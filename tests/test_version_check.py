import unittest
from unittest.mock import Mock, patch

from main import CURRENT_VERSION, check_version


class VersionCheckTests(unittest.TestCase):
    @patch("main.requests.get")
    def test_update_is_returned_without_showing_ui(self, get):
        response = Mock()
        response.json.return_value = {"version": "99.0.0"}
        get.return_value = response

        self.assertEqual(check_version(), (CURRENT_VERSION, "99.0.0"))
        response.raise_for_status.assert_called_once()

    @patch("main.requests.get", side_effect=Exception("offline"))
    def test_unexpected_transport_failure_does_not_escape(self, get):
        # Third-party transports can raise a non-Requests exception. Startup
        # must remain usable even when the update service is unavailable.
        self.assertIsNone(check_version())


if __name__ == "__main__":
    unittest.main()
