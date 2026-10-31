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
        } else if (response.status >= 400 && response.status < 500 && response.status !== 429) {
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
