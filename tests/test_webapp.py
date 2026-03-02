import unittest
from unittest import mock

from webapp import _try_bind_server, build_tracker_response


class WebAppTests(unittest.TestCase):
    def test_requires_claim_id(self):
        with self.assertRaises(ValueError):
            build_tracker_response({})


if __name__ == "__main__":
    unittest.main()


class ServerBindTests(unittest.TestCase):
    def test_try_bind_falls_back_on_permission_error(self):
        first = PermissionError(13, "forbidden")
        second_server = object()

        with mock.patch("webapp.ThreadingHTTPServer", side_effect=[first, second_server]) as server_cls:
            server, port = _try_bind_server("127.0.0.1", [8000, 8080])

        self.assertIs(server, second_server)
        self.assertEqual(port, 8080)
        self.assertEqual(server_cls.call_count, 2)

    def test_try_bind_raises_after_exhausting_ports(self):
        err = OSError("blocked")
        err.winerror = 10013

        with mock.patch("webapp.ThreadingHTTPServer", side_effect=err):
            with self.assertRaises(RuntimeError):
                _try_bind_server("127.0.0.1", [8000, 8080])
