const cronMessages = {
  "15 */6 * * *": { kind: "scheduled_ai_training", timeframe: "M1", min_accuracy: 0.52 },
  "30 2 * * *": { kind: "scheduled_ai_training", timeframe: "M1", min_accuracy: 0.52 },
  "*/15 * * * *": { kind: "ingest_sentiment" },
  "* * * * *": { kind: "ingest_orderbook" },
};

const RETRY_DELAY_SECONDS = 60;
const WEBHOOK_TIMEOUT_MS = 15_000;

export default {
  async scheduled(controller, env, ctx) {
    if (env.AI_TRAINING_DISPATCH_ACTIVE !== "true") {
      console.log("Legacy AI dispatcher schedule disabled; unified background scheduler owns AI schedules");
      return;
    }
    // Keep cron events as queue producers only. Python model training runs in
    // AlgoBot's Celery runtime; Cloudflare Workers must never pretend to run
    // scikit-learn/XGBoost jobs themselves.
    const message = cronMessages[controller.cron];
    if (!message) {
      console.error("Unrecognized AlgoBot cron trigger; no job dispatched", controller.cron);
      return;
    }
    ctx.waitUntil(env.AI_TRAINING_QUEUE.send({
      ...message,
      requested_at: new Date(controller.scheduledTime || Date.now()).toISOString(),
      cron: controller.cron || null,
    }));
  },

  async queue(batch, env) {
    const missing = [
      "ALGOBOT_TRAINING_URL",
      "AI_TRAINING_WEBHOOK_TOKEN",
    ].filter(name => !String(env[name] || "").trim());
    for (const message of batch.messages) {
      if (missing.length) {
        console.error("Legacy AI dispatcher configuration missing; message retained", { missing });
        message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
        continue;
      }
      let response;
      try {
        response = await fetch(env.ALGOBOT_TRAINING_URL, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.AI_TRAINING_WEBHOOK_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(message.body),
          signal: AbortSignal.timeout(WEBHOOK_TIMEOUT_MS),
        });
      } catch (error) {
        console.error("AlgoBot training dispatch transport failure", {
          messageId: message.id,
          error: String(error),
        });
        message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
        continue;
      }

      if (response.ok) {
        message.ack();
        continue;
      }

      // Only syntactically/semantically invalid requests are terminal. In
      // particular, 404 can mean a deployment is still rolling out, and 401/
      // 403 can mean a secret has not propagated yet: retain and retry them.
      if ([400, 422].includes(response.status)) {
        console.error("AlgoBot rejected a malformed training message", {
          messageId: message.id,
          status: response.status,
        });
        message.ack();
        continue;
      }

      console.error("AlgoBot training webhook is not ready; queue message retained", {
        messageId: message.id,
        status: response.status,
      });
      message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
    }
  },
};
