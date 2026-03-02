import unittest

from webapp import build_tracker_response


class WebAppTests(unittest.TestCase):
    def test_requires_claim_id(self):
        with self.assertRaises(ValueError):
            build_tracker_response({})


if __name__ == "__main__":
    unittest.main()
