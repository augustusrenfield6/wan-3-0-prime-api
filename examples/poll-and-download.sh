#!/usr/bin/env bash
# Poll one job until done, then save the MP4 atomically. Safe to rerun with the same request_id.
set -euo pipefail

: "${WAN_API_KEY:?Set WAN_API_KEY first}"
BASE="${WAN_BASE_URL:-https://argolink.io/v1}"
REQUEST_ID="${1:?Usage: $0 REQUEST_ID OUTPUT_FILE}"
OUTPUT="${2:?Usage: $0 REQUEST_ID OUTPUT_FILE}"
MAX_POLLS="${MAX_POLLS:-180}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"

for ((poll = 1; poll <= MAX_POLLS; poll++)); do
  RESPONSE=$(curl --fail-with-body --silent --show-error "$BASE/videos/$REQUEST_ID" \
    -H "Authorization: Bearer $WAN_API_KEY")
  STATUS=$(jq -r '.status // "unknown"' <<<"$RESPONSE")
  echo "poll $poll: $STATUS $(jq -r '.progress // empty' <<<"$RESPONSE")" >&2
  case "$STATUS" in
    done)
      mkdir -p "$(dirname "$OUTPUT")"
      curl --fail-with-body --silent --show-error --location "$BASE/videos/$REQUEST_ID/content" \
        -H "Authorization: Bearer $WAN_API_KEY" -o "$OUTPUT.part"
      mv -- "$OUTPUT.part" "$OUTPUT"
      jq '.usage' <<<"$RESPONSE"
      exit 0
      ;;
    failed|expired)
      jq '{request_id, status, error}' <<<"$RESPONSE" >&2
      exit 1
      ;;
    *) sleep "$SLEEP_SECONDS" ;;
  esac
done

echo "still pending; poll $REQUEST_ID again later instead of resubmitting" >&2
exit 2
