import { DurableObject } from "cloudflare:workers";

const REQUEST_TIMEOUT_MS = 10_000;
const RETRY_DELAY_SECONDS = 10;

export default {
  async fetch() {
    return new Response("Not found", { status: 404 });
  },

  async scheduled(controller, env, ctx) {
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
        } else if ([400, 422].includes(response.status)) {
          console.error("Market tick rejected as invalid", { id: message.id, status: response.status });
          message.ack();
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
        for (const [index, symbol] of symbols.entries()) {
          socket.send(JSON.stringify({ ticks: symbol, subscribe: 1, req_id: index + 1 }));
        }
      });
      socket.addEventListener("message", event => {
        this.handleMessage(event.data).catch(error => {
          console.error("Could not queue Deriv tick", String(error));
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
    if (message.error || message.msg_type !== "tick") return;
    const tick = message.tick || {};
    if (!tick.symbol || tick.quote == null || tick.epoch == null) return;
    await this.env.MARKET_TICK_QUEUE.send({
      symbol: String(tick.symbol),
      quote: tick.quote,
      bid: tick.bid ?? null,
      ask: tick.ask ?? null,
      epoch: tick.epoch,
      volume: tick.volume ?? 0,
    });
  }
}
