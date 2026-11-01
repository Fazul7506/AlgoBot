import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = path => readFile(resolve(root, path), "utf8");
const parseConfig = async path => JSON.parse(await read(path));
const errors = [];
const check = (condition, message) => {
  if (!condition) errors.push(message);
};

const [market, scheduler, legacy] = await Promise.all([
  parseConfig("cloudflare/market-stream/wrangler.jsonc"),
  parseConfig("cloudflare/background-scheduler/wrangler.jsonc"),
  parseConfig("cloudflare/ai-training-dispatcher/wrangler.jsonc"),
]);

check(market.name === "algobot-market-stream", "Market-stream Worker name mismatch");
check(scheduler.name === "algobot-background-scheduler", "Scheduler Worker name mismatch");
check(legacy.name === "algobot-ai-training-dispatcher", "Legacy dispatcher Worker name mismatch");

check(market.vars?.CLOUDFLARE_MARKET_STREAM_ACTIVE === "false", "Market stream must default to disabled");
check(scheduler.vars?.CLOUDFLARE_SCHEDULER_ACTIVE === "false", "Unified scheduler must default to disabled");
check(scheduler.vars?.ENABLE_EXECUTION_QUEUE_RECOVERY === "false", "Execution queue recovery must default to disabled");
check(legacy.vars?.AI_TRAINING_DISPATCH_ACTIVE === "false", "Legacy AI dispatcher must default to disabled");

const queueCheck = (config, queueName, dlqName, producerBinding, requiredConsumer = true) => {
  const producers = config.queues?.producers || [];
  const consumers = config.queues?.consumers || [];
  check(producers.some(item => item.queue === queueName && item.binding === producerBinding),
    `${config.name}: missing producer binding ${producerBinding} -> ${queueName}`);
  if (requiredConsumer) {
    const consumer = consumers.find(item => item.queue === queueName);
    check(Boolean(consumer), `${config.name}: missing consumer for ${queueName}`);
    if (consumer) {
      check(Number.isInteger(consumer.max_retries) && consumer.max_retries > 0,
        `${config.name}: consumer retries must be positive`);
      check(Number.isInteger(consumer.max_batch_size) && consumer.max_batch_size > 0,
        `${config.name}: consumer batch size must be positive`);
      check(consumer.dead_letter_queue === dlqName,
        `${config.name}: consumer must route exhausted retries to ${dlqName}`);
    }
  }
};

queueCheck(market, "algobot-market-ticks", "algobot-market-ticks-dlq", "MARKET_TICK_QUEUE");
queueCheck(scheduler, "algobot-background-tasks", "algobot-background-tasks-dlq", "ALGOBOT_TASK_QUEUE");
queueCheck(legacy, "algobot-ai-training", "algobot-ai-training-dlq", "AI_TRAINING_QUEUE");

const doBinding = (config, bindingName, className) => {
  check((config.durable_objects?.bindings || []).some(
    item => item.name === bindingName && item.class_name === className
  ), `${config.name}: missing Durable Object binding ${bindingName} -> ${className}`);
  check((config.migrations || []).some(item =>
    (item.new_sqlite_classes || []).includes(className) ||
    (item.new_classes || []).includes(className)
  ), `${config.name}: missing Durable Object migration for ${className}`);
};
doBinding(market, "MARKET_STREAM_COORDINATOR", "MarketStreamCoordinator");
doBinding(scheduler, "SCHEDULER_COORDINATOR", "SchedulerCoordinator");

const marketSource = await read("cloudflare/market-stream/src/index.js");
const schedulerSource = await read("cloudflare/background-scheduler/src/index.js");
const dispatcherSource = await read("apps/automation/cloudflare_hooks.py");
const trainingHookSource = await read("apps/ai_engine/cloudflare_hooks.py");
const marketDocs = await read("cloudflare/market-stream/README.md");
const schedulerDocs = await read("cloudflare/README.md");

const requiredSchedules = [
  ["ai-training-every-6-hours", "apps.ai_engine.tasks.scheduled_ai_training"],
  ["ai-training-daily", "apps.ai_engine.tasks.scheduled_ai_training"],
  ["ai-sentiment-every-15-minutes", "apps.ai_engine.tasks.ingest_market_sentiment"],
  ["ai-orderbook-every-minute", "apps.ai_engine.tasks.ingest_orderbook_depth"],
  ["ai-data-health-every-15-minutes", "apps.ai_engine.tasks.check_ai_data_health"],
  ["ai-model-degradation-every-15-minutes", "apps.ai_engine.tasks.check_model_degradation"],
  ["ai-resolve-predictions-every-5-minutes", "apps.ai_engine.tasks.resolve_prediction_outcomes"],
  ["telegram-watchdog-every-minute", "apps.notifications.tasks.telegram_watchdog"],
  ["telegram-recover-stuck-every-5-minutes", "apps.notifications.tasks.recover_stuck_notifications"],
  ["automation-due-schedules-every-30-seconds", "apps.automation.tasks.process_due_scheduled_tasks"],
  ["execution-queue-recovery-every-30-seconds", "apps.execution.process_execution_queue"],
];
for (const [scheduleId, taskName] of requiredSchedules) {
  check(schedulerSource.includes(scheduleId), `Scheduler definition missing schedule: ${scheduleId}`);
  check(dispatcherSource.includes(scheduleId), `Django allowlist missing schedule: ${scheduleId}`);
  check(schedulerSource.includes(taskName), `Scheduler definition missing task: ${taskName}`);
  check(dispatcherSource.includes(taskName), `Django task allowlist missing task: ${taskName}`);
}
for (const [label, url] of [
  ["market symbols endpoint", market.vars?.ALGOBOT_MARKET_SYMBOLS_URL],
  ["market tick endpoint", market.vars?.ALGOBOT_MARKET_TICK_URL],
  ["task dispatch endpoint", scheduler.vars?.ALGOBOT_TASK_DISPATCH_URL],
  ["legacy training endpoint", legacy.vars?.ALGOBOT_TRAINING_URL],
]) {
  try {
    const parsed = new URL(String(url || ""));
    check(parsed.protocol === "https:" && Boolean(parsed.hostname), `${label} must be a valid HTTPS URL`);
  } catch {
    check(false, `${label} must be a valid HTTPS URL`);
  }
}
try {
  const deriv = new URL(String(market.vars?.DERIV_PUBLIC_WS_URL || ""));
  check(deriv.protocol === "wss:" && Boolean(deriv.hostname), "Deriv public stream URL must be a valid WSS URL");
} catch {
  check(false, "Deriv public stream URL must be a valid WSS URL");
}

for (const [label, source, required] of [
  ["market stream", marketSource, ["MARKET_STREAM_CONTROL_TOKEN", "CLOUDFLARE_MARKET_STREAM_TOKEN", "ALGOBOT_MARKET_SYMBOLS_URL", "ALGOBOT_MARKET_TICK_URL", "DERIV_PUBLIC_WS_URL"]],
  ["scheduler", schedulerSource, ["ALGOBOT_TASK_DISPATCH_URL", "ALGOBOT_TASK_DISPATCH_TOKEN", "ALGOBOT_TASK_QUEUE", "ALGOBOT_TASK_DLQ_QUEUE"]],
]) {
  for (const token of required) check(source.includes(token), `${label}: required configuration reference missing: ${token}`);
}
check(marketDocs.includes("MARKET_STREAM_CONTROL_TOKEN") && marketDocs.includes("CLOUDFLARE_MARKET_STREAM_TOKEN"),
  "Market-stream documentation must describe both required secrets");
check(schedulerDocs.includes("CLOUDFLARE_SCHEDULER_ACTIVE=false"),
  "Cloudflare migration documentation must state the scheduler's safe default");
check(dispatcherSource.includes("ALLOWED_SCHEDULES") && dispatcherSource.includes("ALLOWED_TASKS"),
  "Django task dispatch must use both schedule and task allowlists");
check(trainingHookSource.includes("CLOUDFLARE_TRAINING_WEBHOOK_TOKEN"),
  "Legacy training webhook must authenticate with its configured token");

if (errors.length) {
  console.error("Cloudflare architecture preflight failed:");
  for (const error of errors) console.error(` - ${error}`);
  process.exitCode = 1;
} else {
  console.log("Cloudflare architecture preflight passed.");
  console.log("Checked three Worker configs, safe activation defaults, Queue/DLQ bindings,");
  console.log("consumer retry policies, Durable Object bindings/migrations, and dispatch guards.");
  console.log("This is a source/configuration check only; it does not verify live Cloudflare or Render state.");
}
