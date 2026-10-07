"""MCP server (stdio) exposing Wan 3.0 Prime to Claude Code, Cursor, Codex and other MCP clients.

Needs the MCP Python SDK 2.x (`pip install "mcp>=2,<3"`, Python 3.10+). In SDK 1.x the
server class was called FastMCP; 2.x renamed it to MCPServer.

    WAN_API_KEY=... python mcp_server.py
"""

from typing import Any, Callable, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from wan_api import PRICE_PER_SECOND, WanPrimeAPI, WanPrimeAPIError, estimate_cost

mcp = MCPServer(
    "wan-3-prime",
    instructions=(
        "Generate videos with Wan 3.0 Prime. Submit with text_to_video or reference_to_video, "
        "then poll get_video_status every 10-15 s until status is done, failed or expired, "
        "then call download_video. Never resubmit a job that already has a request_id. "
        "Prime takes no first/last frame; ratios are 16:9, 1:1 and 9:16; 4-30 s; 480p, 720p or 1080p."
    ),
)


def _client() -> WanPrimeAPI:
    return WanPrimeAPI()  # reads WAN_API_KEY and optional WAN_BASE_URL from the server's environment


def _run(call: Callable[[], Any]) -> Any:
    """Turn client errors into ToolError so the model sees the reason and can fix its call."""
    try:
        return call()
    except WanPrimeAPIError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool()
def text_to_video(prompt: str, duration: int = 5, resolution: str = "720p", aspect_ratio: str = "16:9") -> Dict[str, Any]:
    """Start a Wan 3.0 Prime text-to-video job. duration 4-30 s; resolution 480p, 720p or 1080p;
    aspect_ratio 16:9, 1:1 or 9:16. Returns request_id and the estimated cost in USD."""
    job = _run(lambda: _client().text_to_video(prompt, duration=duration, resolution=resolution,
                                               aspect_ratio=aspect_ratio))
    return {**job, "estimated_cost_usd": estimate_cost(duration, resolution)}


@mcp.tool()
def reference_to_video(
    prompt: str,
    reference_images: Optional[List[str]] = None,
    reference_videos: Optional[List[str]] = None,
    reference_audios: Optional[List[str]] = None,
    duration: int = 5,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
) -> Dict[str, Any]:
    """Start a job guided by HTTPS reference media (up to 10 images, 5 videos, 5 audio clips, 20 total;
    audio needs an image or video beside it). Name them in the prompt as @Image 1, @Video 1, @Audio 1.
    Reference video seconds are billed like output seconds."""
    return _run(lambda: _client().reference_to_video(
        prompt,
        reference_images=reference_images or [],
        reference_videos=reference_videos or [],
        reference_audios=reference_audios or [],
        duration=duration,
        resolution=resolution,
        aspect_ratio=aspect_ratio,
    ))


@mcp.tool()
def get_video_status(request_id: str) -> Dict[str, Any]:
    """Read a job once: pending (with progress 0-99), done (with usage), failed or expired (with error)."""
    return _run(lambda: _client().get_result(request_id))


@mcp.tool()
def download_video(request_id: str, path: str) -> Dict[str, Any]:
    """Save a finished job's MP4 to a local path. Fails with HTTP 409 while the job is still pending."""
    saved = _run(lambda: _client().download(request_id, path))
    return {"path": str(saved), "bytes": saved.stat().st_size}


@mcp.tool()
def price_table() -> Dict[str, float]:
    """USD per billed second for each Wan 3.0 Prime tier (read 2026-10-07; the model page is authoritative)."""
    return dict(PRICE_PER_SECOND)


if __name__ == "__main__":
    mcp.run()  # stdio transport
