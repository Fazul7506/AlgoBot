export interface Env {
  AI_TRAINING_QUEUE: Queue;
  ALGOBOT_TRAINING_URL: string;
  AI_TRAINING_WEBHOOK_TOKEN: string;
}

const trainingMessage = {
  kind: "scheduled_ai_training",
  timeframe: "M1",
  min_accuracy: 0.52,
  requested_at: new Date().toISOString(),
};

export default {
  async scheduled(_controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(env.AI_TRAINING_QUEUE.send(trainingMessage));
  },

  async queue(batch: MessageBatch, env: Env) {
    for (const message of batch.messages) {
      try {
        const response = await fetch(env.ALGOBOT_TRAINING_URL, {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${env.AI_TRAINING_WEBHOOK_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(message.body),
        });
        if (response.ok) {
          message.ack();
        } else if (response.status >= 400 && response.status < 500 && response.status !== 429) {
          // Permanent request/configuration failures must not loop forever.
          console.error("AlgoBot training webhook rejected message", response.status);
          message.ack();
        } else {
          message.retry({ delaySeconds: 60 });
        }
      } catch (error) {
        console.error("AlgoBot training dispatch failed", error);
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};
