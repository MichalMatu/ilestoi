import unittest
from io import BytesIO

from app.http import request_body
from core.uploads import parse_multipart_form, parse_multipart_stream


def multipart_body(content: bytes) -> bytes:
    return (
        b"--sample\r\n"
        b'Content-Disposition: form-data; name="lat"\r\n\r\n'
        b"51.1\r\n--sample\r\n"
        b'Content-Disposition: form-data; name="file"; filename="photo.jpg"\r\n'
        b"Content-Type: image/jpeg\r\n\r\n" + content + b"\r\n--sample--\r\n"
    )


class TrackingStream(BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.requested_sizes = []

    def read(self, size=-1):
        self.requested_sizes.append(size)
        return super().read(size)


class MultipartStreamingTests(unittest.TestCase):
    def test_streamed_form_matches_legacy_parser_without_full_body_read(self):
        body = multipart_body(b"a" * 180_000)
        stream = TrackingStream(body)
        expected = parse_multipart_form("multipart/form-data; boundary=sample", body)
        actual = parse_multipart_stream(
            "multipart/form-data; boundary=sample", stream, len(body), max_body_bytes=len(body)
        )
        self.assertEqual(actual, expected)
        self.assertGreater(len(stream.requested_sizes), 1)
        self.assertTrue(all(0 < size <= 65536 for size in stream.requested_sizes))

    def test_stream_rejects_oversize_before_read(self):
        stream = TrackingStream(multipart_body(b"a"))
        with self.assertRaisesRegex(ValueError, "limit"):
            parse_multipart_stream("multipart/form-data; boundary=sample", stream, 4000, max_body_bytes=100)
        self.assertEqual(stream.requested_sizes, [])

    def test_stream_rejects_truncated_body(self):
        body = multipart_body(b"a")
        with self.assertRaisesRegex(ValueError, "Niekompletny"):
            parse_multipart_stream(
                "multipart/form-data; boundary=sample", TrackingStream(body[:-5]), len(body), max_body_bytes=10000
            )

    def test_http_reader_uses_bounded_chunks(self):
        body = multipart_body(b"x" * 100_000)
        stream = TrackingStream(body)
        handler = type("Handler", (), {})()
        handler.headers = {
            "Content-Type": "multipart/form-data; boundary=sample",
            "Content-Length": str(len(body)),
        }
        handler.rfile = stream
        fields, photos = request_body.read_multipart_form(handler, max_body_bytes=len(body))
        self.assertEqual(fields, {"lat": "51.1"})
        self.assertEqual(len(photos[0].data), 100_000)
        self.assertLessEqual(max(stream.requested_sizes), 65536)


if __name__ == "__main__":
    unittest.main()
