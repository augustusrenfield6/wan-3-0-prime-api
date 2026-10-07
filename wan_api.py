"""Python client for Alibaba Wan 3.0 Prime (`wan-3-prime`) over the async /v1/videos protocol.

Prime is the fast lane of Wan 3.0: text-to-video and reference-to-video only.
This route takes no first or last frame, offers 16:9, 1:1 and 9:16, renders
4-30 s and always adds a soundtrack. Use `wan-3` for frames, edits, seeds or
silent output.
"""

from __future__ import annotations

import math
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union
from urllib.parse import quote

import requests

MODEL_ID = "wan-3-prime"
DEFAULT_BASE_URL = "https://argolink.io/v1"

RESOLUTIONS = ("480p", "720p", "1080p")
ASPECT_RATIOS = ("16:9", "1:1", "9:16")
MIN_SECONDS, MAX_SECONDS = 4, 30
MAX_PROMPT_CHARACTERS = 20_000
MAX_IMAGES, MAX_VIDEOS, MAX_AUDIOS, MAX_ASSETS = 10, 5, 5, 20
MAX_VIDEO_PLUS_OUTPUT_SECONDS = 30

# USD per billed second, read from https://argolink.io/en/models/wan-3-prime on 2026-10-07.
PRICE_PER_SECOND = {"480p": 0.051, "720p": 0.11, "1080p": 0.21}

TERMINAL_FAILURES = ("failed", "expired")


class WanPrimeAPIError(RuntimeError):
    """A validation, HTTP, upload or terminal-job error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: Any = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.request_id = request_id


def estimate_cost(duration: int, resolution: str = "720p", reference_video_seconds: float = 0) -> float:
    """Output seconds plus reference-video seconds (fraction dropped) times the tier rate."""
    if resolution not in PRICE_PER_SECOND:
        raise WanPrimeAPIError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
    return round((duration + math.floor(reference_video_seconds)) * PRICE_PER_SECOND[resolution], 4)


class WanPrimeAPI:
    """Client for one API key.

    Submits are never retried automatically: a POST that timed out may still have
    created a billable job. Polling and downloading are safe to repeat.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
        timeout: Union[float, tuple] = 30,
        poll_interval: float = 10,
    ) -> None:
        self.api_key = api_key or os.getenv("WAN_API_KEY")
        if not self.api_key:
            raise WanPrimeAPIError("WAN_API_KEY is required")
        self.base_url = (base_url or os.getenv("WAN_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.poll_interval = poll_interval

    # -- HTTP -----------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        headers.update(kwargs.pop("headers", {}))
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                timeout=kwargs.pop("timeout", self.timeout),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise WanPrimeAPIError(f"network error on {method} {path}: {exc}") from exc
        if response.status_code >= 400:
            payload = _json_or_text(response)
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            raise WanPrimeAPIError(
                f"HTTP {response.status_code}{' ' + code if code else ''}: {error or payload}",
                status_code=response.status_code,
                payload=payload,
            )
        return response

    def _post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        decoded = _json_or_text(self._request("POST", path, json=body))
        if not isinstance(decoded, dict):
            raise WanPrimeAPIError("expected a JSON object", payload=decoded)
        return decoded

    # -- validation -------------------------------------------------------------

    @staticmethod
    def _base(prompt: str, duration: int, resolution: str, aspect_ratio: str) -> Dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise WanPrimeAPIError("prompt is required")
        if len(prompt) > MAX_PROMPT_CHARACTERS:
            raise WanPrimeAPIError(f"prompt must be at most {MAX_PROMPT_CHARACTERS} characters")
        if isinstance(duration, bool) or not isinstance(duration, int) or not MIN_SECONDS <= duration <= MAX_SECONDS:
            raise WanPrimeAPIError(f"duration must be a whole number from {MIN_SECONDS} to {MAX_SECONDS} seconds")
        if resolution not in RESOLUTIONS:
            raise WanPrimeAPIError(f"resolution must be one of {', '.join(RESOLUTIONS)}")
        if aspect_ratio not in ASPECT_RATIOS:
            raise WanPrimeAPIError(f"Wan 3.0 Prime accepts aspect_ratio {', '.join(ASPECT_RATIOS)} only")
        return {"model": MODEL_ID, "prompt": prompt, "duration": duration,
                "resolution": resolution, "aspect_ratio": aspect_ratio}

    @staticmethod
    def _urls(urls: Sequence[str]) -> List[Dict[str, str]]:
        for url in urls:
            if not isinstance(url, str) or not url.startswith("https://"):
                raise WanPrimeAPIError(f"media must be an https:// URL, got {url!r}; upload local files first")
        return [{"url": url} for url in urls]

    # -- jobs -------------------------------------------------------------------

    def text_to_video(
        self,
        prompt: str,
        *,
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
    ) -> Dict[str, Any]:
        """Submit a prompt-only job. Returns {"request_id": ...}."""
        return self._post_json("/videos/generations", self._base(prompt, duration, resolution, aspect_ratio))

    def reference_to_video(
        self,
        prompt: str,
        *,
        reference_images: Sequence[str] = (),
        reference_videos: Sequence[str] = (),
        reference_audios: Sequence[str] = (),
        duration: int = 5,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
    ) -> Dict[str, Any]:
        """Submit a job guided by HTTPS reference media; name them as @Image 1, @Video 1, @Audio 1."""
        body = self._base(prompt, duration, resolution, aspect_ratio)
        if not (reference_images or reference_videos or reference_audios):
            raise WanPrimeAPIError("pass at least one reference, or use text_to_video")
        if reference_audios and not (reference_images or reference_videos):
            raise WanPrimeAPIError("audio cannot be the only reference on wan-3-prime; add an image or a video")
        if len(reference_images) > MAX_IMAGES or len(reference_videos) > MAX_VIDEOS or len(reference_audios) > MAX_AUDIOS:
            raise WanPrimeAPIError(f"at most {MAX_IMAGES} images, {MAX_VIDEOS} videos and {MAX_AUDIOS} audio clips")
        if len(reference_images) + len(reference_videos) + len(reference_audios) > MAX_ASSETS:
            raise WanPrimeAPIError(f"at most {MAX_ASSETS} reference assets per request")
        for field, urls in (("reference_images", reference_images),
                            ("reference_videos", reference_videos),
                            ("reference_audios", reference_audios)):
            if urls:
                body[field] = self._urls(urls)
        return self._post_json("/videos/generations", body)

    def image_to_video(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Not available on this route: start_image / end_image return 400 on wan-3-prime."""
        raise WanPrimeAPIError(
            "wan-3-prime takes no first or last frame; pass the image as a reference_image, "
            "or use the wan-3 model for first-frame and first/last-frame videos"
        )

    def upload_file(self, path: Union[str, Path], *, kind: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """Upload a local JPEG/PNG, MP4/MOV or WAV/MP3 through a free upload ticket."""
        source = Path(path)
        if kind not in ("image", "video", "audio"):
            raise WanPrimeAPIError("kind must be image, video or audio")
        if not source.is_file() or source.stat().st_size == 0:
            raise WanPrimeAPIError(f"not a non-empty file: {source}")
        mime = content_type or mimetypes.guess_type(source.name)[0]
        if mime == "audio/x-wav":
            mime = "audio/wav"
        if not mime:
            raise WanPrimeAPIError("pass content_type; it cannot be guessed from the file name")
        ticket = self._post_json("/media/uploads", {
            "model": MODEL_ID, "type": kind, "content_type": mime, "size_bytes": source.stat().st_size,
        })
        if not ticket.get("upload_url") or not ticket.get("media_url"):
            raise WanPrimeAPIError("upload ticket lacks upload_url or media_url", payload=ticket)
        try:
            with source.open("rb") as handle:  # the signed URL authorizes itself: no bearer token
                put = self.session.put(ticket["upload_url"], data=handle,
                                       headers={"Content-Type": mime}, timeout=self.timeout)
        except requests.RequestException as exc:
            raise WanPrimeAPIError(f"upload of {source.name} failed: {exc}") from exc
        if put.status_code >= 400:
            raise WanPrimeAPIError(f"signed upload returned HTTP {put.status_code}", status_code=put.status_code)
        return {"media_url": ticket["media_url"], "content_type": mime, "size_bytes": source.stat().st_size}

    def get_result(self, request_id: str) -> Dict[str, Any]:
        """One status read: pending, done, failed or expired."""
        decoded = _json_or_text(self._request("GET", f"/videos/{_safe_id(request_id)}"))
        if not isinstance(decoded, dict):
            raise WanPrimeAPIError("expected a JSON object from the status endpoint", payload=decoded)
        return decoded

    def wait_for_completion(
        self,
        request_id: str,
        *,
        max_wait_seconds: float = 1800,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Poll until done; raise on failed or expired, or when max_wait_seconds runs out."""
        deadline = time.monotonic() + max_wait_seconds
        while True:
            result = self.get_result(request_id)
            status = result.get("status")
            if status == "done":
                return result
            if status in TERMINAL_FAILURES:
                raise WanPrimeAPIError(f"job {status}: {result.get('error')}", payload=result, request_id=request_id)
            if on_progress:
                on_progress(result)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WanPrimeAPIError("still pending at the deadline; poll the same request_id later",
                                       payload=result, request_id=request_id)
            time.sleep(min(self.poll_interval, remaining))

    def download(self, request_id: str, destination: Union[str, Path]) -> Path:
        """Stream the finished MP4 to a .part file, then rename it into place."""
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        response = self._request("GET", f"/videos/{_safe_id(request_id)}/content",
                                 headers={"Accept": "video/mp4"}, stream=True)
        try:
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    if chunk:
                        handle.write(chunk)
            partial.replace(target)
        except (OSError, requests.RequestException) as exc:
            partial.unlink(missing_ok=True)
            raise WanPrimeAPIError(f"download to {target} failed: {exc}", request_id=request_id) from exc
        finally:
            getattr(response, "close", lambda: None)()
        return target


def _json_or_text(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _safe_id(request_id: str) -> str:
    if not request_id or "/" in request_id:
        raise WanPrimeAPIError("request_id is required and must not contain '/'")
    return quote(request_id, safe="")
