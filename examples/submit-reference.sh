#!/usr/bin/env bash
# Reference job from HTTPS URLs: one image, plus an optional clip and an optional audio track.
# Audio alone is rejected on wan-3-prime, so the image is required here.
set -euo pipefail

: "${WAN_API_KEY:?Set WAN_API_KEY first}"
BASE="${WAN_BASE_URL:-https://argolink.io/v1}"
IMAGE_URL="${1:?Usage: $0 IMAGE_URL [VIDEO_URL] [AUDIO_URL]}"
VIDEO_URL="${2:-}"
AUDIO_URL="${3:-}"

jq -n --arg image "$IMAGE_URL" --arg video "$VIDEO_URL" --arg audio "$AUDIO_URL" '
  {model: "wan-3-prime",
   prompt: "The character in @Image 1 walks through a neon night market, the camera tracking beside them",
   duration: 8, resolution: "720p", aspect_ratio: "9:16",
   reference_images: [{url: $image}]}
  | if $video != "" then .reference_videos = [{url: $video}] | .prompt += ", moving like @Video 1" else . end
  | if $audio != "" then .reference_audios = [{url: $audio}] | .prompt += ", in time with @Audio 1" else . end' \
  | curl --fail-with-body --silent --show-error \
      -X POST "$BASE/videos/generations" \
      -H "Authorization: Bearer $WAN_API_KEY" \
      -H 'Content-Type: application/json' \
      --data-binary @- \
  | jq -r '.request_id'
