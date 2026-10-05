import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wan_api import WanPrimeAPI, WanPrimeAPIError


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

    def get(self, url, **kwargs):
        self.calls.append(("GET_STREAM", url, kwargs))
        return FakeResponse({}, 200, b"video-bytes")


class WanPrimeAPITest(unittest.TestCase):
    def test_submit_uses_canonical_model_and_explicit_fields(self):
        session = FakeSession([FakeResponse({"request_id": "req_1", "status": "pending"}, 202)])
        api = WanPrimeAPI("test-key", session=session)
        result = api.text_to_video("A calm ocean", duration=6, resolution="1080p")
        self.assertEqual(result["request_id"], "req_1")
        payload = session.calls[0][2]["json"]
        self.assertEqual(payload["model"], "wan-3-prime")
        self.assertEqual(payload["duration"], 6)
        self.assertEqual(payload["aspect_ratio"], "16:9")

    def test_frame_mode_forces_adaptive_ratio(self):
        session = FakeSession([FakeResponse({"request_id": "req_2", "status": "pending"}, 202)])
        api = WanPrimeAPI("test-key", session=session)
        api.image_to_video("Move forward", start_image="https://example.invalid/start.jpg")
        payload = session.calls[0][2]["json"]
        self.assertEqual(payload["aspect_ratio"], "adaptive")
        self.assertEqual(payload["start_image"], {"url": "https://example.invalid/start.jpg"})

    def test_validation_happens_before_network(self):
        session = FakeSession([])
        api = WanPrimeAPI("test-key", session=session)
        with self.assertRaises(WanPrimeAPIError):
            api.reference_to_video("No assets")
        self.assertEqual(session.calls, [])

    def test_wait_returns_done_after_pending(self):
        session = FakeSession([
            FakeResponse({"request_id": "req_3", "status": "pending"}),
            FakeResponse({"request_id": "req_3", "status": "done", "video": {"url": "x"}}),
        ])
        api = WanPrimeAPI("test-key", session=session, poll_interval=0)
        result = api.wait_for_completion("req_3", max_wait_seconds=1)
        self.assertEqual(result["status"], "done")

    def test_upload_uses_signed_put_without_bearer(self):
        session = FakeSession([FakeResponse({"upload_url": "https://example.invalid/t", "media_url": "https://example.invalid/a.jpg"})])
        api = WanPrimeAPI("test-key", session=session)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "a.jpg"
            path.write_bytes(b"jpg")
            result = api.upload_file(path, kind="image", content_type="image/jpeg")
        self.assertEqual(result["media_url"], "https://example.invalid/a.jpg")
        self.assertNotIn("Authorization", session.put_calls[0][1]["headers"])

    def test_download_renames_completed_stream(self):
        session = FakeSession([])
        api = WanPrimeAPI("test-key", session=session)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "result.mp4"
            api.download("req_4", target)
            self.assertEqual(target.read_bytes(), b"video-bytes")
            self.assertFalse(target.with_name("result.mp4.part").exists())


if __name__ == "__main__":
    unittest.main()
