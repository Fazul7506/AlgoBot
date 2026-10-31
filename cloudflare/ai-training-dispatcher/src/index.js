const trainingMessage = {
  kind: "scheduled_ai_training",
  timeframe: "M1",
  min_accuracy: 0.52,
};

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(env.AI_TRAINING_QUEUE.send({
      ...trainingMessage,
      requested_at: new Date().toISOString(),
    }));
  },

  async queue(batch, env) {
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
        } else if ([400, 404, 422].includes(response.status)) {
          console.error("AlgoBot training webhook rejected an invalid request", response.status);
          message.ack();
        } else {
          // Auth, throttling, deployment and server failures are retryable.
          message.retry({ delaySeconds: 60 });
        }
      } catch (error) {
        console.error("AlgoBot training dispatch failed", error);
        message.retry({ delaySeconds: 60 });
      }
    }
  },
};
