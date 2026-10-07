import asyncio
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wan_api import WanPrimeAPI, WanPrimeAPIError, estimate_cost


class FakeResponse:
    def __init__(self, payload=None, status_code=200, body=b""):
        self._payload = payload
        self.status_code = status_code
        self.text = body.decode() if body else ""
        self._body = body

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    def iter_content(self, chunk_size=1):
        yield self._body


class FakeSession:
    """Answers queued responses in order and records every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.put_calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def put(self, url, **kwargs):
        self.put_calls.append((url, kwargs))
        return FakeResponse({}, 200)


def accepted(request_id="req_1"):
    return FakeResponse({"request_id": request_id}, 202)


class SubmitTest(unittest.TestCase):
    def test_text_job_uses_new_base_url_and_explicit_fields(self):
        session = FakeSession([accepted()])
        WanPrimeAPI("k", session=session).text_to_video("A calm ocean", duration=6, resolution="1080p")
        method, url, kwargs = session.calls[0]
        self.assertEqual((method, url), ("POST", "https://argolink.io/v1/videos/generations"))
        self.assertEqual(kwargs["json"], {"model": "wan-3-prime", "prompt": "A calm ocean", "duration": 6,
                                          "resolution": "1080p", "aspect_ratio": "16:9"})
        self.assertNotIn("generate_audio", kwargs["json"])  # always on for Prime; false would be a 400

    def test_only_three_ratios(self):
        api = WanPrimeAPI("k", session=FakeSession([]))
        for ratio in ("adaptive", "4:3", "3:4", "21:9"):
            with self.assertRaises(WanPrimeAPIError):
                api.text_to_video("x", aspect_ratio=ratio)

    def test_duration_range_is_4_to_30(self):
        api = WanPrimeAPI("k", session=FakeSession([]))
        for seconds in (2, 3, 31, 5.0, True):
            with self.assertRaises(WanPrimeAPIError):
                api.text_to_video("x", duration=seconds)

    def test_frames_are_not_offered(self):
        with self.assertRaisesRegex(WanPrimeAPIError, "no first or last frame"):
            WanPrimeAPI("k", session=FakeSession([])).image_to_video("x", start_image="https://a.test/1.png")

    def test_reference_rules_checked_before_network(self):
        session = FakeSession([])
        api = WanPrimeAPI("k", session=session)
        with self.assertRaisesRegex(WanPrimeAPIError, "only reference"):
            api.reference_to_video("x", reference_audios=["https://a.test/a.mp3"])
        with self.assertRaises(WanPrimeAPIError):
            api.reference_to_video("x", reference_images=["https://a.test/i.png"] * 11)
        with self.assertRaises(WanPrimeAPIError):
            api.reference_to_video("x", reference_images=["http://insecure.test/i.png"])
        self.assertEqual(session.calls, [])

    def test_reference_job_body(self):
        session = FakeSession([accepted()])
        WanPrimeAPI("k", session=session).reference_to_video(
            "@Image 1 dances like @Video 1", reference_images=["https://a.test/i.png"],
            reference_videos=["https://a.test/v.mp4"], aspect_ratio="9:16")
        body = session.calls[0][2]["json"]
        self.assertEqual(body["reference_videos"], [{"url": "https://a.test/v.mp4"}])
        self.assertEqual(body["aspect_ratio"], "9:16")


class LifecycleTest(unittest.TestCase):
    def test_wait_returns_done_after_pending(self):
        session = FakeSession([
            FakeResponse({"request_id": "req_3", "status": "pending", "progress": 30}),
            FakeResponse({"request_id": "req_3", "status": "done", "usage": {"billed_seconds": 5}}),
        ])
        seen = []
        result = WanPrimeAPI("k", session=session, poll_interval=0).wait_for_completion(
            "req_3", max_wait_seconds=5, on_progress=seen.append)
        self.assertEqual(result["usage"]["billed_seconds"], 5)
        self.assertEqual(seen[0]["progress"], 30)
        self.assertTrue(session.calls[0][1].endswith("/v1/videos/req_3"))

    def test_failed_and_expired_raise(self):
        for state in ("failed", "expired"):
            session = FakeSession([FakeResponse({"status": state, "error": {"code": "capacity_unavailable"}})])
            with self.assertRaises(WanPrimeAPIError) as caught:
                WanPrimeAPI("k", session=session).wait_for_completion("req_x")
            self.assertEqual(caught.exception.payload["status"], state)

    def test_http_error_carries_code(self):
        session = FakeSession([FakeResponse({"error": {"code": "request_unsupported", "message": "seed"}}, 400)])
        with self.assertRaises(WanPrimeAPIError) as caught:
            WanPrimeAPI("k", session=session).text_to_video("x")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("request_unsupported", str(caught.exception))

    def test_upload_uses_signed_put_without_bearer(self):
        session = FakeSession([FakeResponse({"upload_url": "https://store.test/t", "media_url": "https://media.test/a.jpg"})])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "a.jpg"
            path.write_bytes(b"jpg")
            result = WanPrimeAPI("k", session=session).upload_file(path, kind="image")
        self.assertEqual(result["media_url"], "https://media.test/a.jpg")
        self.assertEqual(session.calls[0][2]["json"]["content_type"], "image/jpeg")
        self.assertNotIn("Authorization", session.put_calls[0][1]["headers"])

    def test_download_renames_completed_stream(self):
        session = FakeSession([FakeResponse(None, 200, b"video-bytes")])
        with TemporaryDirectory() as directory:
            target = Path(directory) / "result.mp4"
            WanPrimeAPI("k", session=session).download("req_4", target)
            self.assertEqual(target.read_bytes(), b"video-bytes")
            self.assertFalse(target.with_name("result.mp4.part").exists())
        self.assertTrue(session.calls[0][1].endswith("/v1/videos/req_4/content"))

    def test_cost(self):
        self.assertAlmostEqual(estimate_cost(10, "720p"), 1.10)
        self.assertAlmostEqual(estimate_cost(5, "480p", reference_video_seconds=2.4), 7 * 0.051)


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP SDK not installed (pip install 'mcp>=2,<3')")
class McpServerTest(unittest.TestCase):
    def test_tools_are_listed_and_callable(self):
        import mcp_server
        from mcp import Client

        async def run():
            async with Client(mcp_server.mcp) as client:
                names = sorted(tool.name for tool in (await client.list_tools()).tools)
                prices = await client.call_tool("price_table", {})
                return names, prices

        names, prices = asyncio.run(run())
        self.assertEqual(names, ["download_video", "get_video_status", "price_table",
                                 "reference_to_video", "text_to_video"])
        self.assertFalse(prices.is_error)


if __name__ == "__main__":
    unittest.main()
