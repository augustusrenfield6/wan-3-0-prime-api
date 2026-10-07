# Wan 3.0 Prime API — from $0.051/s (480p)

**Alibaba Wan 3.0 Prime is live on [ArgoLink](https://argolink.io/gh-wan-3-0-prime-api)**: $0.051/s at 480p, $0.11/s at 720p and $0.21/s at 1080p, 21–25% below Alibaba Cloud's international list price. Prime is the faster lane of Wan 3.0: a prompt, optionally with reference images, clips and audio, becomes a 4–30 second video with its own soundtrack.

[Wan 3.0 Prime model page →](https://argolink.io/en/models/wan-3-prime) · [Prices](#price-per-second) · [Install](#install) · [Prime vs Wan 3.0](#wan-30-prime-vs-wan-30) · [MCP server](#mcp-server) · [FAQ](#faq)

A small Python client ([`wan_api.py`](./wan_api.py)), an MCP server for agent tools ([`mcp_server.py`](./mcp_server.py)), curl scripts in [`examples/`](./examples) and offline tests. It speaks the async `/v1/videos` protocol: submit, poll, download.

<sub>Last checked: 2026-10-07 against the pages linked in the tables.</sub>

## At a glance

| | |
|---|---|
| Model ID | `wan-3-prime` |
| Modes | text to video · reference to video (images, video, audio). No first or last frame and no video edit on this route |
| Duration | 4–30 s in whole seconds, default 5 |
| Resolution | 480p · 720p · 1080p, default 720p |
| Aspect ratio | 16:9 · 1:1 · 9:16, default 16:9 |
| References | ≤ 10 images, ≤ 5 videos, ≤ 5 audio clips, ≤ 20 in total. Clips 1–15 s each and 15 s per kind; output plus reference video ≤ 30 s. Audio needs an image or video beside it |
| Prompt | required, up to 20,000 characters; name assets `@Image 1`, `@Video 1`, `@Audio 1` |
| Sound | always on (AAC stereo); `generate_audio: false` returns 400 |
| Output | one 24 fps H.264 MP4 per request |
| Rejected with 400 | `start_image`, `end_image`, `seed`, `watermark: true`, `n` other than 1 |

## Price per second

| Provider | 480p | 720p | 1080p | 10 s at 720p |
|---|---:|---:|---:|---:|
| **[ArgoLink](https://argolink.io/en/models/wan-3-prime)** | **$0.051** | **$0.11** | **$0.21** | **$1.10** |
| [Alibaba Cloud Model Studio](https://www.alibabacloud.com/help/en/model-studio/wan3-0-video-prime), Singapore (international) | $0.068 | $0.14 | $0.28 | $1.40 |
| Alibaba Cloud Model Studio, US (Virginia) and other global regions | $0.0636 | $0.1272 | $0.2544 | $1.27 |
| [WaveSpeedAI](https://wavespeed.ai/models/alibaba/wan-3.0-prime/text-to-video) | $0.075 | $0.15 | $0.30 | $1.50 |
| [MuAPI](https://muapi.ai/wan-3) | $0.068 | $0.14 | $0.28 | $1.40 |

<sub>All pages read 2026-10-07 (the Alibaba page was last updated 2026-09-28 and shows list prices without promotions). Against the Singapore list the ArgoLink rate is 25% lower at 480p and 1080p and 21% lower at 720p; against the global-region list it is 20%, 14% and 17% lower.</sub>

## Install

```bash
git clone https://github.com/augustusrenfield6/wan-3-0-prime-api
cd wan-3-0-prime-api
python -m pip install -e .          # client: Python 3.9+, requests
python -m pip install -e ".[mcp]"   # adds the MCP server: Python 3.10+, mcp 2.x
export WAN_API_KEY=your-key         # an ArgoLink API key
```

`WAN_BASE_URL` (default `https://argolink.io/v1`) points the client at any other server with the same protocol.

## Quick start

```python
from wan_api import WanPrimeAPI, estimate_cost

api = WanPrimeAPI()
job = api.text_to_video(
    "A cinematic tracking shot of a red fox crossing a snowy forest at sunrise, breath steaming",
    duration=8,
    resolution="720p",
    aspect_ratio="16:9",
)
result = api.wait_for_completion(job["request_id"], on_progress=lambda s: print(s.get("progress"), "%"))
api.download(job["request_id"], "fox.mp4")
print(result["usage"], estimate_cost(8, "720p"))   # 8 billed seconds, $0.88
```

## Reference to video

```python
job = api.reference_to_video(
    "The woman in @Image 1 walks into the café from @Video 1 and orders, in time with @Audio 1",
    reference_images=["https://example.com/woman.jpg"],
    reference_videos=["https://example.com/cafe-6s.mp4"],
    reference_audios=["https://example.com/voice.mp3"],
    duration=10,
    aspect_ratio="9:16",
)
# billed seconds = 10 output + 6 reference video = 16 -> 16 x $0.11 = $1.76 at 720p
```

Local files go through a free upload ticket first:

```python
media = api.upload_file("woman.jpg", kind="image")      # PUTs to a signed URL, no bearer token
job = api.reference_to_video("@Image 1 waves at the camera", reference_images=[media["media_url"]])
```

Upload limits: JPEG or PNG up to 20 MiB; MP4 or MOV up to 100 MiB and 1–15 s; WAV or MP3 up to 15 MB and 1–15 s. The `upload_url` is valid for 15 minutes and the `media_url` for seven days.

## API surface

| Method | Does |
|---|---|
| `text_to_video(prompt, duration, resolution, aspect_ratio)` | submit a prompt-only job, return `{"request_id"}` |
| `reference_to_video(prompt, reference_images, reference_videos, reference_audios, ...)` | submit with HTTPS references |
| `upload_file(path, kind)` | upload a local asset, return its `media_url` |
| `get_result(request_id)` | read the status once |
| `wait_for_completion(request_id, max_wait_seconds, on_progress)` | poll until `done`; raise on `failed` / `expired` |
| `download(request_id, path)` | stream the MP4 to `path.part`, then rename |
| `estimate_cost(duration, resolution, reference_video_seconds)` | dollars at the rates above |
| `image_to_video(...)` | raises: frames are not accepted on `wan-3-prime` |

Every method validates locally first (ratio, duration, tier, counts, HTTPS URLs), so a bad request fails before it reaches the API. Submits are never retried by the client: a POST that timed out may still have created a job, so poll before you resend.

### curl

```bash
BASE=https://argolink.io/v1
ID=$(./examples/submit-text.sh "Paper lanterns rise over a river at dusk" 6 720p 16:9)
./examples/poll-and-download.sh "$ID" lanterns.mp4
```

[`submit-reference.sh`](./examples/submit-reference.sh) and [`upload-and-submit.sh`](./examples/upload-and-submit.sh) cover references; all four scripts need `curl` and `jq`.

## Wan 3.0 Prime vs Wan 3.0

Both are Alibaba Wan 3.0 on the same endpoint; the model ID picks the lane.

| | `wan-3-prime` | `wan-3` |
|---|---|---|
| Positioning | faster turnaround | full feature set |
| Duration | 4–30 s | 2–30 s |
| First / last frame | not on this route (400) | yes |
| Edit an existing video | no | yes (`omni_reference_task_type: "edit"`) |
| Aspect ratios | 16:9, 1:1, 9:16 | 21:9, 16:9, 4:3, 1:1, 3:4, 9:16, adaptive |
| Audio as the only reference | no | yes |
| `seed` | rejected | accepted |
| Silent output | no | `generate_audio: false` |
| Price 480p / 720p / 1080p | $0.051 / $0.11 / $0.21 | $0.038 / $0.075 / $0.15 |

Alibaba Cloud's own Prime documentation lists first-frame and first/last-frame input; the `wan-3-prime` route described here does not accept them, so send frames to `wan-3`.

## MCP server

`mcp_server.py` runs over stdio and exposes `text_to_video`, `reference_to_video`, `get_video_status`, `download_video` and `price_table`. It reads `WAN_API_KEY` from its own environment and never takes a key as a tool argument.

Claude Code:

```bash
claude mcp add --transport stdio --env WAN_API_KEY=your-key wan-3-prime -- python /path/to/wan-3-0-prime-api/mcp_server.py
```

Cursor (`.cursor/mcp.json` or `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "wan-3-prime": {
      "command": "python",
      "args": ["/path/to/wan-3-0-prime-api/mcp_server.py"],
      "env": { "WAN_API_KEY": "${env:WAN_API_KEY}" }
    }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.wan-3-prime]
command = "python"
args = ["/path/to/wan-3-0-prime-api/mcp_server.py"]
env_vars = ["WAN_API_KEY"]
```

The server needs the MCP Python SDK 2.x. In 1.x the class was `FastMCP` (`mcp.server.fastmcp`), which 2.x renamed to `MCPServer`.

## Billing rules

- Per output second at the tier rate, multiplied by the length.
- Reference video seconds are added, with the fraction of their total dropped: 5 s output with a 2.4 s clip bills 7 s.
- Reference images and audio are free; uploads are free.
- A failed, rejected or expired job is not billed. The finished job's `usage` holds `output_seconds`, `reference_video_seconds` and `billed_seconds`.

## Status values

`pending` (with `progress` 0–99 and, once known, `estimated_seconds_remaining`), `done` (with `video.url` and `usage`), `failed` (with `error.code`, `error.message`, `error.retryable`) and `expired`. The content endpoint answers 409 `job_video_not_ready` until the job is done and 424 `job_failed` after a failure.

## FAQ

**Can Wan 3.0 Prime start from my image?**
Not as a first frame on this route: `start_image` and `end_image` return 400. Pass the image as `reference_images` (it guides the subject without being frame one), or use `wan-3` for true first-frame and first/last-frame videos.

**Why is 4:3 or adaptive rejected?**
Prime accepts 16:9, 1:1 and 9:16 only. `wan-3` adds 21:9, 4:3, 3:4 and adaptive.

**Can I get a silent clip?**
No, every Prime video carries a generated stereo track. Remove it afterwards with `ffmpeg -i in.mp4 -an -c:v copy out.mp4`, or use `wan-3` with `generate_audio: false`.

**What does a 30-second 1080p Prime clip cost?**
30 × $0.21 = $6.30 here, against $8.40 at Alibaba Cloud's Singapore list price.

**How long can a reference clip be?**
1–15 s each and 15 s in total, and the output plus the reference videos may not exceed 30 s.

**The old example used `running` and `api.argolink.io`. Which is right?**
Neither: the documented statuses are `pending`, `done`, `failed` and `expired`, and the base URL is `https://argolink.io/v1`.

## Tests

```bash
python -m pip install -e ".[test]"   # add ",mcp" to also run the MCP server test
python -m pytest
```

The tests use a fake HTTP session; no key or network is needed.

## License

MIT
