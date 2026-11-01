const SCHEDULES = {
  "automation-due-schedules-every-30-seconds": {
    cron: "* * * * *",
    task: "apps.automation.tasks.process_due_scheduled_tasks",
    kwargs: { limit: 100 },
    queue: "celery",
    expires: 55,
  },
  "execution-queue-recovery-every-30-seconds": {
    cron: "* * * * *",
    task: "apps.execution.process_execution_queue",
    kwargs: { batch_size: 10 },
    queue: "celery",
    expires: 55,
    requires_explicit_enable: true,
  },
  "ai-data-health-every-15-minutes": {
    cron: "*/15 * * * *",
    task: "apps.ai_engine.tasks.check_ai_data_health",
    kwargs: { timeframe: "M1" },
    queue: "celery",
  },
  "ai-resolve-predictions-every-5-minutes": {
    cron: "*/5 * * * *",
    task: "apps.ai_engine.tasks.resolve_prediction_outcomes",
    kwargs: { timeframe: "M1", horizon_candles: 1, batch_size: 500 },
    queue: "celery",
  },
  "telegram-watchdog-every-minute": {
    cron: "* * * * *",
    task: "apps.notifications.tasks.telegram_watchdog",
    queue: "celery",
  },
  "telegram-recover-stuck-every-5-minutes": {
    cron: "*/5 * * * *",
    task: "apps.notifications.tasks.recover_stuck_notifications",
    queue: "celery",
  },
};

const RETRY_DELAY_SECONDS = 60;
const REQUEST_TIMEOUT_MS = 12_000;

export default {
  async scheduled(controller, env, ctx) {
    const matches = Object.entries(SCHEDULES).filter(([, item]) => item.cron === controller.cron);
    if (!matches.length) {
      console.error("Unknown scheduler cron; no messages produced", { cron: controller.cron });
      return;
    }
    ctx.waitUntil(Promise.all(matches.map(async ([scheduleId, schedule]) => {
      if (schedule.requires_explicit_enable && env.ENABLE_EXECUTION_QUEUE_RECOVERY !== "true") {
        console.log("Execution queue recovery remains disabled until explicitly enabled", { scheduleId });
        return;
      }
      await env.ALGOBOT_TASK_QUEUE.send({
        schedule_id: scheduleId,
        task: schedule.task,
        kwargs: schedule.kwargs || {},
        queue: schedule.queue || "celery",
        expires: schedule.expires || null,
        scheduled_at: new Date(controller.scheduledTime || Date.now()).toISOString(),
        scheduled_minute: Math.floor((controller.scheduledTime || Date.now()) / 60_000),
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

      if ([400, 422].includes(response.status)) {
        console.error("Task dispatch rejected invalid message", { messageId: message.id, status: response.status });
        message.ack();
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
