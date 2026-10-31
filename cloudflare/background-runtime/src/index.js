import { Container, getContainer } from "@cloudflare/containers";

const REQUIRED_RUNTIME_VARS = [
  "DATABASE_URL",
  "REDIS_URL",
  "SECRET_KEY",
  "BREVO_API_KEY",
  "DERIV_OAUTH_CLIENT_ID",
  "DERIV_APP_ID",
  "DERIV_REDIRECT_URI",
];

const OPTIONAL_RUNTIME_VARS = [
  "DJANGO_SETTINGS_MODULE", "DJANGO_ENV", "USE_REDIS", "USE_CELERY",
  "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS", "CORS_ALLOWED_ORIGINS",
  "BASE_URL", "ALGO_API_BASE_URL", "DB_POOL_MIN_SIZE", "DB_POOL_MAX_SIZE",
  "DB_POOL_TIMEOUT", "REDIS_CHANNEL_MAX_CONNECTIONS",
  "CLOUDFLARE_R2_ACCOUNT_ID", "CLOUDFLARE_R2_ACCESS_KEY_ID",
  "CLOUDFLARE_R2_SECRET_ACCESS_KEY", "CLOUDFLARE_R2_BUCKET",
  "AI_MODEL_PREFIX", "AI_MODEL_SIGNING_KEY", "CLOUDFLARE_TRAINING_WEBHOOK_TOKEN",
  "AI_SENTIMENT_RSS_URLS", "AI_SENTIMENT_SYMBOL_KEYWORDS_JSON",
  "ORDER_BOOK_API_URL", "ORDER_BOOK_API_TOKEN", "ORDER_BOOK_SYMBOLS",
  "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "TELEGRAM_WEBHOOK_SECRET",
  "TELEGRAM_MODE", "TELEGRAM_API_TIMEOUT", "TELEGRAM_RETRY_MAX_ATTEMPTS",
  "DERIV_PUBLIC_WS_URL", "DERIV_API_URL", "DERIV_OAUTH_REDIRECT_URI",
  "CREDENTIALS_ENCRYPTION_KEY", "ALLOW_LIVE_TRADING",
];

const ROLE_CONFIG = [
  {
    name: "Celery Worker",
    binding: "CELERY_WORKER",
    entrypoint: [
      "celery", "-A", "deriv_platform.celery", "worker",
      "--loglevel=INFO", "-Q", "celery", "--concurrency=1",
      "--prefetch-multiplier=1", "--max-tasks-per-child=50",
      "--hostname=cloudflare-worker@%h",
    ],
  },
  {
    name: "Celery Beat",
    binding: "CELERY_BEAT",
    entrypoint: [
      "celery", "-A", "deriv_platform.celery", "beat",
      "--loglevel=INFO", "--pidfile=/tmp/algobot-celerybeat.pid",
    ],
  },
  {
    name: "Deriv Market Stream",
    binding: "DERIV_MARKET_STREAM",
    entrypoint: ["python", "manage.py", "run_market_stream"],
  },
];

function buildRuntimeEnv(env) {
  const missing = REQUIRED_RUNTIME_VARS.filter(
    (key) => typeof env[key] !== "string" || env[key].length === 0,
  );
  if (missing.length) {
    throw new Error(
      "Cloudflare background runtime is not configured. Missing Worker secrets/vars: " +
      missing.join(", "),
    );
  }

  const runtimeEnv = {
    DJANGO_SETTINGS_MODULE: "deriv_platform.settings",
    DJANGO_ENV: "production",
    USE_REDIS: "true",
    USE_CELERY: "true",
    DB_POOL_MIN_SIZE: "0",
    DB_POOL_MAX_SIZE: "2",
    DB_POOL_TIMEOUT: "20",
  };

  for (const key of OPTIONAL_RUNTIME_VARS) {
    if (typeof env[key] === "string" && env[key].length > 0) {
      runtimeEnv[key] = env[key];
    }
  }
  for (const key of REQUIRED_RUNTIME_VARS) {
    runtimeEnv[key] = env[key];
  }

  return runtimeEnv;
}

export class CeleryWorkerContainer extends Container {
  sleepAfter = "10m";
  entrypoint = ROLE_CONFIG[0].entrypoint;
  enableInternet = true;
}

export class CeleryBeatContainer extends Container {
  sleepAfter = "10m";
  entrypoint = ROLE_CONFIG[1].entrypoint;
  enableInternet = true;
}

export class DerivMarketStreamContainer extends Container {
  sleepAfter = "10m";
  entrypoint = ROLE_CONFIG[2].entrypoint;
  enableInternet = true;
}

async function ensureContainer(env, role, runtimeEnv) {
  const binding = env[role.binding];
  if (!binding) {
    throw new Error("Cloudflare Container binding is missing for " + role.name);
  }

  // A stable singleton name prevents duplicate Beat schedulers and streams.
  const container = getContainer(binding, "algobot-production");
  await container.start({
    envVars: runtimeEnv,
    enableInternet: true,
  });

  console.log("Background container start/keepalive requested", {
    role: role.name,
    configuredConcurrency: role.name === "Celery Worker" ? 1 : undefined,
  });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return Response.json({
        status: "ok",
        service: "algobot-background-runtime",
        roles: ROLE_CONFIG.map(({ name }) => name),
        note: "Worker reachability only; this does not prove each container process is healthy.",
      });
    }
    return new Response("Not found", { status: 404 });
  },

  async scheduled(controller, env) {
    const runtimeEnv = buildRuntimeEnv(env);
    const outcomes = await Promise.allSettled(
      ROLE_CONFIG.map((role) => ensureContainer(env, role, runtimeEnv)),
    );

    const failures = outcomes.flatMap((outcome, index) =>
      outcome.status === "rejected"
        ? [{ role: ROLE_CONFIG[index].name, error: String(outcome.reason) }]
        : [],
    );

    if (failures.length) {
      console.error("One or more AlgoBot background containers failed to start", {
        scheduledTime: controller.scheduledTime,
        failures,
      });
      throw new Error(
        "Failed to start " + failures.map((failure) => failure.role).join(", "),
      );
    }

    console.log("AlgoBot background runtime keepalive completed", {
      scheduledTime: controller.scheduledTime,
      roles: ROLE_CONFIG.map(({ name }) => name),
    });
  },
};
