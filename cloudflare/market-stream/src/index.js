import { DurableObject } from "cloudflare:workers";

const REQUEST_TIMEOUT_MS = 10_000;
const RETRY_DELAY_SECONDS = 10;
const MAX_PENDING_TICK_WRITES = 1_000;
const MAX_QUEUE_SEND_ATTEMPTS = 3;
const MAX_TICK_AGE_SECONDS = 30;
const FUTURE_TICK_TOLERANCE_SECONDS = 30;

export default {
  async fetch() {
    return new Response("Not found", { status: 404 });
  },

  async scheduled(controller, env, ctx) {
    if (env.CLOUDFLARE_MARKET_STREAM_ACTIVE !== "true") {
      console.log("Cloudflare Deriv stream remains disabled until deliberate cutover");
      return;
    }
    const id = env.MARKET_STREAM_COORDINATOR.idFromName("deriv-public-stream");
    const coordinator = env.MARKET_STREAM_COORDINATOR.get(id);
    ctx.waitUntil(coordinator.fetch("https://market-stream.internal/start", {
      method: "POST",
      headers: { Authorization: `Bearer ${env.MARKET_STREAM_CONTROL_TOKEN}` },
    }));
  },

  async queue(batch, env) {
    for (const message of batch.messages) {
      try {
        const response = await fetch(env.ALGOBOT_MARKET_TICK_URL, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.CLOUDFLARE_MARKET_STREAM_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ tick: message.body }),
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        });
        if (response.ok) {
          message.ack();
        } else if ([400, 413, 422].includes(response.status)) {
          try {
            await env.MARKET_TICK_DLQ_QUEUE.send({
              source: "algobot-market-stream",
              original_message_id: message.id,
              failure_status: response.status,
              failed_at: new Date().toISOString(),
              body: message.body,
            });
            console.error("Invalid market tick moved to dead-letter queue", {
              id: message.id, status: response.status,
            });
            message.ack();
          } catch (error) {
            console.error("Could not dead-letter invalid market tick", {
              id: message.id, error: String(error),
            });
            message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
          }
        } else {
          message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
        }
      } catch (error) {
        console.error("Market tick ingestion transport failure", { id: message.id, error: String(error) });
        message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
      }
    }
  },
};

export class MarketStreamCoordinator extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.socket = null;
    this.connecting = false;
    this.pendingTickWrites = Promise.resolve();
    this.pendingTickCount = 0;
  }

  async fetch(request) {
    if (request.headers.get("Authorization") !== `Bearer ${this.env.MARKET_STREAM_CONTROL_TOKEN}`) {
      return new Response("Unauthorized", { status: 401 });
    }
    await this.ensureConnected();
    return Response.json({ status: this.socket?.readyState === WebSocket.OPEN ? "connected" : "connecting" });
  }

  async alarm() {
    await this.ensureConnected();
  }

  async ensureConnected() {
    if (this.connecting || this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) {
      return;
    }
    this.connecting = true;
    try {
      const symbolsResponse = await fetch(this.env.ALGOBOT_MARKET_SYMBOLS_URL, {
        headers: { Authorization: `Bearer ${this.env.CLOUDFLARE_MARKET_STREAM_TOKEN}` },
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      if (!symbolsResponse.ok) throw new Error(`Symbol endpoint returned ${symbolsResponse.status}`);
      const { symbols } = await symbolsResponse.json();
      if (!Array.isArray(symbols) || symbols.length === 0) throw new Error("No active Deriv symbols returned");

      const socket = new WebSocket(this.env.DERIV_PUBLIC_WS_URL);
      this.socket = socket;
      socket.addEventListener("open", () => {
        // Deriv's public ticks endpoint accepts a symbol array. One subscription
        // request avoids flooding the socket with one request per market and
        // makes the subscription set explicit for reconnects.
        socket.send(JSON.stringify({ ticks: symbols, subscribe: 1, req_id: 1 }));
      });
      socket.addEventListener("message", event => {
        if (this.pendingTickCount >= MAX_PENDING_TICK_WRITES) {
          console.error("Deriv tick queue producer is backpressured; closing stream to bound memory", {
            pending: this.pendingTickCount,
          });
          try { socket.close(1013, "Market tick ingestion backpressure"); } catch {}
          return;
        }

        this.pendingTickCount += 1;
        const write = this.pendingTickWrites.then(() => this.handleMessage(event.data));
        this.pendingTickWrites = write
          .catch(error => {
            console.error("Could not queue Deriv tick after bounded retries", String(error));
            // Stop receiving more ticks when the durable Queue cannot accept
            // them. The close handler schedules a reconnect; the failure is
            // visible in logs rather than silently continuing with a dead path.
            try { socket.close(1013, "Market tick queue unavailable"); } catch {}
          })
          .finally(() => {
            this.pendingTickCount = Math.max(0, this.pendingTickCount - 1);
          });
      });
      socket.addEventListener("error", () => {
        try { socket.close(); } catch {}
      });
      socket.addEventListener("close", () => {
        if (this.socket === socket) this.socket = null;
        this.ctx.storage.setAlarm(Date.now() + 5_000).catch(error => {
          console.error("Could not schedule stream reconnect", String(error));
        });
      });
    } catch (error) {
      console.error("Deriv stream connection failed", String(error));
      await this.ctx.storage.setAlarm(Date.now() + 5_000);
    } finally {
      this.connecting = false;
    }
  }

  async handleMessage(raw) {
    if (typeof raw !== "string") return;
    let message;
    try { message = JSON.parse(raw); } catch { return; }
    if (message.error) {
      console.error("Deriv public tick subscription returned an error", {
        code: message.error.code,
        message: String(message.error.message || "unknown").slice(0, 200),
      });
      return;
    }
    if (message.msg_type !== "tick") return;
    const tick = message.tick || {};
    const symbol = String(tick.symbol || "").trim();
    const quote = Number(tick.quote);
    const epoch = Number(tick.epoch);
    if (!symbol || symbol.length > 64 || tick.quote == null || tick.epoch == null) return;
    if (!Number.isFinite(quote) || !Number.isSafeInteger(epoch) || epoch <= 0) {
      console.error("Deriv tick failed numeric validation", { symbol });
      return;
    }
    const ageSeconds = Math.floor(Date.now() / 1000) - epoch;
    if (ageSeconds < -FUTURE_TICK_TOLERANCE_SECONDS) {
      console.error("Deriv tick timestamp is too far in the future", { symbol, ageSeconds });
      return;
    }
    if (ageSeconds > MAX_TICK_AGE_SECONDS) {
      console.warn("Dropping stale Deriv tick before persistence", { symbol, ageSeconds });
      return;
    }
    const payload = {
      symbol,
      quote,
      bid: tick.bid ?? null,
      ask: tick.ask ?? null,
      epoch,
      volume: tick.volume ?? 0,
    };
    let lastError;
    for (let attempt = 1; attempt <= MAX_QUEUE_SEND_ATTEMPTS; attempt += 1) {
      try {
        await this.env.MARKET_TICK_QUEUE.send(payload);
        return;
      } catch (error) {
        lastError = error;
        if (attempt < MAX_QUEUE_SEND_ATTEMPTS) {
          await new Promise(resolve => setTimeout(resolve, 250 * (2 ** (attempt - 1))));
        }
      }
    }
    throw lastError || new Error("Market tick Queue send failed");
  }
}
