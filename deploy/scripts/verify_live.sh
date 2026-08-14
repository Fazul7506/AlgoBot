#!/usr/bin/env bash
set -euo pipefail
: "${BASE_URL:?BASE_URL is required}"
curl --fail --silent --show-error "$BASE_URL/health/live/" >/dev/null
curl --fail --silent --show-error "$BASE_URL/health/ready/" >/dev/null
echo "Live and ready health checks passed."
