import test from "node:test";
import assert from "node:assert/strict";
import worker, { SchedulerCoordinator } from "./index.js";

async function scheduled(cron) {
  const messages = [];
  const pending = [];
  let coordinatorStarted = false;
  const env = {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
    ALGOBOT_TASK_DISPATCH_URL: "https://example.invalid/task-dispatch/",
    ALGOBOT_TASK_DISPATCH_TOKEN: "test-token",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
    SCHEDULER_COORDINATOR: {
      idFromName(name) { assert.equal(name, "algobot-background-scheduler"); return "scheduler-id"; },
      get(id) { assert.equal(id, "scheduler-id"); return { async fetch() { coordinatorStarted = true; return new Response("ok"); } }; },
    },
  };
  const ctx = { waitUntil(promise) { pending.push(promise); } };
  await worker.scheduled({ cron, scheduledTime: 1_800_000_000_000 }, env, ctx);
  await Promise.all(pending);
  return { messages, coordinatorStarted };
}

test("every-minute cron starts the durable 30-second scheduler and dispatches Telegram watchdog", async () => {
  const { messages, coordinatorStarted } = await scheduled("* * * * *");
  assert.equal(coordinatorStarted, true);
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-orderbook-every-minute",
    "telegram-watchdog-every-minute",
  ]);
  assert.ok(messages.every(message => Number.isInteger(message.scheduled_minute)));
});

test("five-minute cron dispatches prediction resolution and Telegram recovery", async () => {
  const { messages } = await scheduled("*/5 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-resolve-predictions-every-5-minutes",
    "telegram-recover-stuck-every-5-minutes",
  ]);
});

test("fifteen-minute cron dispatches data health and sentiment ingestion", async () => {
  const { messages } = await scheduled("*/15 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-data-health-every-15-minutes",
    "ai-model-degradation-every-15-minutes",
    "ai-sentiment-every-15-minutes",
  ]);
});

test("unknown cron does not enqueue work", async () => {
  const { messages, coordinatorStarted } = await scheduled("0 0 31 2 *");
  assert.deepEqual(messages, []);
  assert.equal(coordinatorStarted, false);
});

test("durable alarm dispatches automation on 30-second slots and keeps execution recovery off by default", async () => {
  const messages = [];
  const alarms = [];
  const ctx = {
    storage: {
      async getAlarm() { return null; },
      async setAlarm(value) { alarms.push(value); },
    },
  };
  const coordinator = new SchedulerCoordinator(ctx, {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
    ALGOBOT_TASK_DISPATCH_URL: "https://example.invalid/task-dispatch/",
    ALGOBOT_TASK_DISPATCH_TOKEN: "test-token",
    ENABLE_EXECUTION_QUEUE_RECOVERY: "false",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
  });
  await coordinator.alarm();
  assert.equal(messages.length, 1);
  assert.equal(messages[0].schedule_id, "automation-due-schedules-every-30-seconds");
  assert.equal(messages[0].expires, 25);
  assert.ok(Number.isInteger(messages[0].scheduled_minute));
  assert.equal(alarms.length, 1);
});

test("execution queue recovery is emitted only when explicitly enabled", async () => {
  const messages = [];
  const ctx = { storage: { async getAlarm() { return null; }, async setAlarm() {} } };
  await new SchedulerCoordinator(ctx, {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
    ALGOBOT_TASK_DISPATCH_URL: "https://example.invalid/task-dispatch/",
    ALGOBOT_TASK_DISPATCH_TOKEN: "test-token",
    ENABLE_EXECUTION_QUEUE_RECOVERY: "true",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
  }).alarm();
  assert.equal(messages.some(message => message.schedule_id === "execution-queue-recovery-every-30-seconds"), true);
});


test("six-hour AI training schedule is dispatched through the unified task queue", async () => {
  const { messages } = await scheduled("15 */6 * * *");
  assert.deepEqual(messages.map(message => message.schedule_id), ["ai-training-every-6-hours"]);
  assert.equal(messages[0].task, "apps.ai_engine.tasks.scheduled_ai_training");
  assert.deepEqual(messages[0].kwargs, { timeframe: "M1", min_accuracy: 0.52 });
});

test("daily AI training schedule is dispatched through the unified task queue", async () => {
  const { messages } = await scheduled("30 2 * * *");
  assert.deepEqual(messages.map(message => message.schedule_id), ["ai-training-daily"]);
});

test("AI external-signal ingestion shares the unified scheduler and queue", async () => {
  const { messages } = await scheduled("*/15 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-data-health-every-15-minutes",
    "ai-sentiment-every-15-minutes",
  ]);
});


test("active scheduler refuses to emit work when dispatch credentials are missing", async () => {
  const messages = [];
  const pending = [];
  let coordinatorStarted = false;
  const env = {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
    SCHEDULER_COORDINATOR: {
      idFromName() { return "scheduler-id"; },
      get() { return { async fetch() { coordinatorStarted = true; } }; },
    },
  };
  await worker.scheduled(
    { cron: "*/5 * * * *", scheduledTime: 1_800_000_000_000 },
    env,
    { waitUntil(promise) { pending.push(promise); } },
  );
  await Promise.all(pending);
  assert.deepEqual(messages, []);
  assert.equal(coordinatorStarted, false);
});

test("task Queue consumer retains messages when dispatch configuration is missing", async () => {
  let retryOptions = null;
  let acked = false;
  const message = {
    id: "missing-config-message",
    body: { schedule_id: "ai-training-every-6-hours" },
    ack() { acked = true; },
    retry(options) { retryOptions = options; },
  };
  await worker.queue({ messages: [message] }, {});
  assert.deepEqual(retryOptions, { delaySeconds: 60 });
  assert.equal(acked, false);
});

test("30-second coordinator does not enqueue work when dispatch configuration is missing", async () => {
  const messages = [];
  const alarms = [];
  const ctx = {
    storage: {
      async getAlarm() { return null; },
      async setAlarm(value) { alarms.push(value); },
    },
  };
  const coordinator = new SchedulerCoordinator(ctx, {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
  });
  await coordinator.alarm();
  assert.deepEqual(messages, []);
  assert.equal(alarms.length, 1);
});
