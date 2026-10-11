import unittest

from obs_protocol import (
    LEGACY_CAPABILITIES,
    PROTOCOL_VERSION,
    negotiate_plugin,
    prepare_request,
    should_resynchronize,
    validate_response,
)


class ObsProtocolTests(unittest.TestCase):
    def test_request_has_current_protocol_and_client_identity(self):
        request = prepare_request({"event": "hello"})
        self.assertEqual(request["version"], PROTOCOL_VERSION)
        self.assertEqual(request["client"]["name"], "DOSOFT")

    def test_response_must_match_request_id(self):
        response = {"version": 3, "request_id": "autre", "ok": True}
        self.assertEqual(validate_response(response, "attendu"), "request_id_mismatch")

    def test_current_plugin_capabilities_are_negotiated(self):
        response = {
            "version": 3,
            "request_id": "abc",
            "ok": True,
            "data": {
                "plugin_version": "0.3.0",
                "protocol_version": 3,
                "protocol_min": 2,
                "session_id": "session-test",
                "obs_version": "32.0.0",
                "capabilities": ["inventory", "sync_team"],
            },
        }
        result = negotiate_plugin(response)
        self.assertTrue(result["compatible"])
        self.assertFalse(result["legacy"])
        self.assertEqual(result["session_id"], "session-test")
        self.assertEqual(result["obs_version"], "32.0.0")
        self.assertEqual(result["capabilities"], frozenset({"inventory", "sync_team"}))

    def test_installed_v2_plugin_remains_compatible(self):
        response = {
            "version": 2,
            "request_id": "abc",
            "ok": True,
            "data": {"plugin_version": "0.2.0", "scenes": []},
        }
        result = negotiate_plugin(response)
        self.assertTrue(result["compatible"])
        self.assertTrue(result["legacy"])
        self.assertEqual(result["capabilities"], LEGACY_CAPABILITIES)

    def test_future_protocol_is_rejected(self):
        response = {"version": 99, "request_id": "abc", "ok": True}
        self.assertFalse(negotiate_plugin(response)["compatible"])

    def test_new_obs_session_requires_resynchronization(self):
        self.assertTrue(should_resynchronize("ancienne", "nouvelle", True))
        self.assertFalse(should_resynchronize("stable", "stable", True))
        self.assertTrue(should_resynchronize("", "", False))


if __name__ == "__main__":
    unittest.main()
