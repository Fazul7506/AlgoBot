const SCHEDULES = {
  "ai-training-every-6-hours": {
    cron: "15 */6 * * *",
    task: "apps.ai_engine.tasks.scheduled_ai_training",
    kwargs: { timeframe: "M1", min_accuracy: 0.52 },
  },
  "ai-training-daily": {
    cron: "30 2 * * *",
    task: "apps.ai_engine.tasks.scheduled_ai_training",
    kwargs: { timeframe: "M1", min_accuracy: 0.52 },
  },
  "ai-sentiment-every-15-minutes": {
    cron: "*/15 * * * *",
    task: "apps.ai_engine.tasks.ingest_market_sentiment",
    kwargs: {},
  },
  "ai-orderbook-every-minute": {
    cron: "* * * * *",
    task: "apps.ai_engine.tasks.ingest_orderbook_depth",
    kwargs: {},
  },
  "ai-data-health-every-15-minutes": {
    cron: "*/15 * * * *",
    task: "apps.ai_engine.tasks.check_ai_data_health",
    kwargs: { timeframe: "M1" },
  },
  "ai-model-degradation-every-15-minutes": {
    cron: "*/15 * * * *",
    task: "apps.ai_engine.tasks.check_model_degradation",
    kwargs: {},
  },
  "ai-resolve-predictions-every-5-minutes": {
    cron: "*/5 * * * *",
    task: "apps.ai_engine.tasks.resolve_prediction_outcomes",
    kwargs: { timeframe: "M1", horizon_candles: 1, batch_size: 500 },
  },
  "telegram-watchdog-every-minute": {
    cron: "* * * * *",
    task: "apps.notifications.tasks.telegram_watchdog",
    kwargs: {},
  },
  "telegram-recover-stuck-every-5-minutes": {
    cron: "*/5 * * * *",
    task: "apps.notifications.tasks.recover_stuck_notifications",
    kwargs: {},
  },
};

const RETRY_DELAY_SECONDS = 60;
const REQUEST_TIMEOUT_MS = 12_000;

export default {
  async scheduled(controller, env, ctx) {
    if (env.CLOUDFLARE_SCHEDULER_ACTIVE !== "true") {
      console.log("Cloudflare scheduler remains disabled until deliberate cutover");
      return;
    }
    const cron = controller.cron;
    if (cron === "* * * * *") {
      const id = env.SCHEDULER_COORDINATOR.idFromName("algobot-background-scheduler");
      const coordinator = env.SCHEDULER_COORDINATOR.get(id);
      ctx.waitUntil(coordinator.fetch("https://scheduler.internal/start", { method: "POST" }));
    }

    const matches = Object.entries(SCHEDULES).filter(([, item]) => item.cron === cron);
    if (!matches.length) {
      if (cron !== "* * * * *") {
        console.error("Unknown scheduler cron; no messages produced", { cron });
      }
      return;
    }

    ctx.waitUntil(Promise.all(matches.map(async ([scheduleId, schedule]) => {
      const scheduledTime = controller.scheduledTime || Date.now();
      await env.ALGOBOT_TASK_QUEUE.send({
        schedule_id: scheduleId,
        task: schedule.task,
        kwargs: schedule.kwargs,
        queue: "celery",
        expires: null,
        scheduled_at: new Date(scheduledTime).toISOString(),
        scheduled_minute: Math.floor(scheduledTime / 60_000),
      });
    })));
  },

  async queue(batch, env) {
    for (const message of batch.messages) {
      let response;
      try {
        response = await fetch(env.ALGOBOT_TASK_DISPATCH_URL, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${env.ALGOBOT_TASK_DISPATCH_TOKEN}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(message.body),
          signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
        });
      } catch (error) {
        console.error("Task dispatch transport failure", { messageId: message.id, error: String(error) });
        message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
        continue;
      }

      if (response.ok) {
        message.ack();
        continue;
      }

      if ([400, 413, 422].includes(response.status)) {
        try {
          await env.ALGOBOT_TASK_DLQ_QUEUE.send({
            source: "algobot-background-scheduler",
            original_message_id: message.id,
            failure_status: response.status,
            failed_at: new Date().toISOString(),
            body: message.body,
          });
          console.error("Invalid task message moved to dead-letter queue", {
            messageId: message.id, scheduleId: message.body?.schedule_id, status: response.status,
          });
          message.ack();
        } catch (error) {
          console.error("Could not dead-letter invalid task message", {
            messageId: message.id, error: String(error),
          });
          message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
        }
      } else {
        console.error("Task dispatch endpoint unavailable; retaining queue message", {
          messageId: message.id,
          status: response.status,
        });
        message.retry({ delaySeconds: RETRY_DELAY_SECONDS });
      }
    }
  },
};

export class SchedulerCoordinator {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
    if (await this.ctx.storage.getAlarm() === null) {
      await this.ctx.storage.setAlarm(Date.now() + 1_000);
    }
    return Response.json({ status: "scheduled" }, { status: 202 });
  }

  async alarm() {
    if (this.env.CLOUDFLARE_SCHEDULER_ACTIVE !== "true") {
      await this.ctx.storage.setAlarm(Date.now() + 30_000);
      return;
    }
    const scheduledTime = Date.now();
    const slot = Math.floor(scheduledTime / 30_000);
    const common = {
      queue: "celery",
      scheduled_at: new Date(scheduledTime).toISOString(),
      // This integer is a 30-second slot for these two schedules. The Django
      // dispatcher uses it only as an idempotency component.
      scheduled_minute: slot,
    };
    try {
      const sends = [
        this.env.ALGOBOT_TASK_QUEUE.send({
          ...common,
          schedule_id: "automation-due-schedules-every-30-seconds",
          task: "apps.automation.tasks.process_due_scheduled_tasks",
          kwargs: { limit: 100 },
          expires: 25,
        }),
      ];
      if (this.env.ENABLE_EXECUTION_QUEUE_RECOVERY === "true") {
        sends.push(this.env.ALGOBOT_TASK_QUEUE.send({
          ...common,
          schedule_id: "execution-queue-recovery-every-30-seconds",
          task: "apps.execution.process_execution_queue",
          kwargs: { batch_size: 10 },
          expires: 25,
        }));
      }
      await Promise.all(sends);
    } catch (error) {
      console.error("Could not enqueue 30-second scheduled tasks", String(error));
    } finally {
      await this.ctx.storage.setAlarm(Date.now() + 30_000);
    }
  }
};
