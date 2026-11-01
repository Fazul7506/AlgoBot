import test from "node:test";
import assert from "node:assert/strict";
import worker from "./index.js";

async function scheduled(cron, enabled = false) {
  const messages = [];
  let pending = Promise.resolve();
  const env = {
    ENABLE_EXECUTION_QUEUE_RECOVERY: enabled ? "true" : "false",
    ALGOBOT_TASK_QUEUE: {
      async send(message) { messages.push(message); },
    },
  };
  const ctx = { waitUntil(promise) { pending = promise; } };
  await worker.scheduled({ cron, scheduledTime: 1_800_000_000_000 }, env, ctx);
  await pending;
  return messages;
}

test("every-minute cron dispatches automation and Telegram watchdog only", async () => {
  const messages = await scheduled("* * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "automation-due-schedules-every-30-seconds",
    "telegram-watchdog-every-minute",
  ]);
  assert.ok(messages.every(message => Number.isInteger(message.scheduled_minute)));
});

test("five-minute cron dispatches prediction resolution and Telegram recovery", async () => {
  const messages = await scheduled("*/5 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id).sort(), [
    "ai-resolve-predictions-every-5-minutes",
    "telegram-recover-stuck-every-5-minutes",
  ]);
});

test("fifteen-minute cron dispatches data health", async () => {
  const messages = await scheduled("*/15 * * * *");
  assert.deepEqual(messages.map(message => message.schedule_id), [
    "ai-data-health-every-15-minutes",
  ]);
});

test("execution queue recovery remains disabled unless explicitly enabled", async () => {
  assert.equal((await scheduled("* * * * *")).some(
    message => message.schedule_id === "execution-queue-recovery-every-30-seconds"
  ), false);
  assert.equal((await scheduled("* * * * *", true)).some(
    message => message.schedule_id === "execution-queue-recovery-every-30-seconds"
  ), true);
});

test("unknown cron does not enqueue work", async () => {
  assert.deepEqual(await scheduled("0 0 31 2 *"), []);
});
