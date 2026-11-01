import test from "node:test";
import assert from "node:assert/strict";
import worker, { SchedulerCoordinator } from "./index.js";

async function scheduled(cron) {
  const messages = [];
  const pending = [];
  let coordinatorStarted = false;
  const env = {
    CLOUDFLARE_SCHEDULER_ACTIVE: "true",
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
  assert.deepEqual(messages.map(message => message.schedule_id), ["telegram-watchdog-every-minute"]);
  assert.ok(messages.every(message => Number.isInteger(message.scheduled_minute)));
});

test("five-minute cron dispatches prediction resolution and Telegram recovery", async () => {
  const { messages } = await scheduled("*/5 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-resolve-predictions-every-5-minutes",
    "telegram-recover-stuck-every-5-minutes",
  ]);
});

test("fifteen-minute cron dispatches data health", async () => {
  const { messages } = await scheduled("*/15 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id), ["ai-data-health-every-15-minutes"]);
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
    ENABLE_EXECUTION_QUEUE_RECOVERY: "true",
    ALGOBOT_TASK_QUEUE: { async send(message) { messages.push(message); } },
  }).alarm();
  assert.equal(messages.some(message => message.schedule_id === "execution-queue-recovery-every-30-seconds"), true);
});

