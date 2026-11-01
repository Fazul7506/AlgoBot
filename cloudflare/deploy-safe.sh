#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---check}"
ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-}"
API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
API_BASE="https://api.cloudflare.com/client/v4"
QUEUE_NAMES=(
  "algobot-ai-training"
  "algobot-ai-training-dlq"
  "algobot-background-tasks"
  "algobot-background-tasks-dlq"
  "algobot-market-ticks"
  "algobot-market-ticks-dlq"
)

case "$MODE" in
  --check|--apply) ;;
  *)
    echo "Usage: $0 [--check|--apply]" >&2
    exit 2
    ;;
esac

cd "$ROOT_DIR"
node cloudflare/preflight.mjs

for config in \
  cloudflare/ai-training-dispatcher/wrangler.jsonc \
  cloudflare/background-scheduler/wrangler.jsonc \
  cloudflare/market-stream/wrangler.jsonc; do
  echo "Checking Wrangler bundle: $config"
  npx --yes wrangler deploy --dry-run --config "$config"
done

if [[ "$MODE" == "--check" ]]; then
  cat <<'EOF'
Check mode only: no Cloudflare resources were created or deployed.
For an explicit disabled deployment, run this script with --apply after reviewing
the Cloudflare account and confirming that the configured account is correct.
EOF
  exit 0
fi

if [[ -z "$ACCOUNT_ID" || -z "$API_TOKEN" ]]; then
  echo "Refusing --apply: set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN." >&2
  exit 2
fi

echo "Verifying Cloudflare API token and account access (secret values are never printed)."
verification="$(curl --fail --silent --show-error \
  -H "Authorization: Bearer $API_TOKEN" \
  "$API_BASE/accounts/$ACCOUNT_ID/queues?per_page=1000")"

if ! printf '%s' "$verification" | node -e '
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => input += chunk);
process.stdin.on("end", () => {
  try {
    const payload = JSON.parse(input);
    if (payload.success !== true || !Array.isArray(payload.result)) process.exit(1);
  } catch { process.exit(1); }
});
'; then
  echo "Refusing deployment: Cloudflare Queue API access could not be verified." >&2
  exit 2
fi

echo "Creating only missing Queue resources; existing queues are left untouched."
printf '%s' "$verification" | node -e '
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => input += chunk);
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  for (const queue of payload.result) console.log(queue.queue_name);
});
' > /tmp/algobot-cloudflare-queues.txt

for queue in "${QUEUE_NAMES[@]}"; do
  if grep -Fxq "$queue" /tmp/algobot-cloudflare-queues.txt; then
    echo "Queue exists: $queue"
  else
    echo "Creating Queue: $queue"
    curl --fail --silent --show-error -X POST \
      -H "Authorization: Bearer $API_TOKEN" \
      -H "Content-Type: application/json" \
      --data "$(printf '{"queue_name":"%s"}' "$queue")" \
      "$API_BASE/accounts/$ACCOUNT_ID/queues" >/dev/null
  fi
done

# Wrangler config sets all activation gates to false. Never pass --var overrides
# here; enabling any path requires a separate, reviewed cutover after validation.
for config in \
  cloudflare/ai-training-dispatcher/wrangler.jsonc \
  cloudflare/background-scheduler/wrangler.jsonc \
  cloudflare/market-stream/wrangler.jsonc; do
  echo "Deploying disabled Worker from $config"
  npx --yes wrangler deploy --config "$config"
done

cat <<'EOF'
Disabled Worker deployment commands completed.
The script does not set or display secret values and does not enable any trigger.
Before any cutover, configure the documented Worker secrets and matching Render
environment values, then run the live configuration audit and the separate
end-to-end validation plan. Keep execution recovery and live trading disabled.
EOF
