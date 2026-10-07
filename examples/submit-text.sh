#!/usr/bin/env bash
# Prompt-only Wan 3.0 Prime job. Prints the request_id to poll.
set -euo pipefail

: "${WAN_API_KEY:?Set WAN_API_KEY first}"
BASE="${WAN_BASE_URL:-https://argolink.io/v1}"
PROMPT="${1:?Usage: $0 'prompt' [duration 4-30] [480p|720p|1080p] [16:9|1:1|9:16]}"
DURATION="${2:-5}"
RESOLUTION="${3:-720p}"
ASPECT_RATIO="${4:-16:9}"

jq -n --arg prompt "$PROMPT" --argjson duration "$DURATION" --arg resolution "$RESOLUTION" --arg ratio "$ASPECT_RATIO" \
  '{model: "wan-3-prime", prompt: $prompt, duration: $duration, resolution: $resolution, aspect_ratio: $ratio}' \
  | curl --fail-with-body --silent --show-error \
      -X POST "$BASE/videos/generations" \
      -H "Authorization: Bearer $WAN_API_KEY" \
      -H 'Content-Type: application/json' \
      --data-binary @- \
  | jq -r '.request_id'
