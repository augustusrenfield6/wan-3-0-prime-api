#!/usr/bin/env bash
# Upload one local image or video (free ticket + signed PUT), then use it as a reference.
set -euo pipefail

: "${WAN_API_KEY:?Set WAN_API_KEY first}"
BASE="${WAN_BASE_URL:-https://argolink.io/v1}"
FILE="${1:?Usage: $0 FILE image|video}"
KIND="${2:?Usage: $0 FILE image|video}"

case "$(uname -s)" in
  Darwin) SIZE_BYTES=$(stat -f%z "$FILE") ;;
  *) SIZE_BYTES=$(stat -c%s "$FILE") ;;
esac
case "$KIND" in
  image) FIELD=reference_images; MENTION="@Image 1" ;;
  video) FIELD=reference_videos; MENTION="@Video 1" ;;
  *) echo "kind must be image or video (audio cannot be the only reference on wan-3-prime)" >&2; exit 2 ;;
esac
CONTENT_TYPE=$(file --brief --mime-type "$FILE")

TICKET=$(curl --fail-with-body --silent --show-error \
  -X POST "$BASE/media/uploads" \
  -H "Authorization: Bearer $WAN_API_KEY" \
  -H 'Content-Type: application/json' \
  --data "$(jq -n --arg kind "$KIND" --arg type "$CONTENT_TYPE" --argjson size "$SIZE_BYTES" \
    '{model: "wan-3-prime", type: $kind, content_type: $type, size_bytes: $size}')")

# The signed URL authorizes itself: do not print it and do not add the bearer token.
curl --fail-with-body --silent --show-error -X PUT "$(jq -er .upload_url <<<"$TICKET")" \
  -H "Content-Type: $CONTENT_TYPE" --upload-file "$FILE" >/dev/null

jq -n --arg media "$(jq -er .media_url <<<"$TICKET")" --arg field "$FIELD" --arg mention "$MENTION" \
  '{model: "wan-3-prime", prompt: ("A short cinematic shot built around " + $mention + ", slow push-in, soft daylight"),
    duration: 5, resolution: "720p", aspect_ratio: "16:9"} | .[$field] = [{url: $media}]' \
  | curl --fail-with-body --silent --show-error \
      -X POST "$BASE/videos/generations" \
      -H "Authorization: Bearer $WAN_API_KEY" \
      -H 'Content-Type: application/json' \
      --data-binary @- \
  | jq -r '.request_id'
