from collections import deque
import threading
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from dosoft_obs_bridge import DosoftObsBridge


class DummyConfig:
    data = {"obs_integration_enabled": True}


def make_bridge(state="disconnected"):
    bridge = DosoftObsBridge.__new__(DosoftObsBridge)
    bridge.config = DummyConfig()
    bridge.connection_state = state
    bridge._last_state_message = None
    bridge._handshake_in_flight = False
    bridge.capabilities = frozenset()
    bridge._outbox = deque()
    bridge._outbox_condition = threading.Condition()
    bridge._record = Mock()
    return bridge


class ObsBridgeNoiseTests(unittest.TestCase):
    def test_identical_connection_state_is_recorded_only_once(self):
        bridge = make_bridge("connecting")

        bridge._set_state("disconnected", "OBS déconnecté")
        bridge._set_state("disconnected", "OBS déconnecté")

        bridge._record.assert_called_once_with("OBS déconnecté", force=False)

    def test_background_commands_are_dropped_until_handshake_is_ready(self):
        bridge = make_bridge("connecting")
        callback = Mock()

        bridge._send_async({"event": "obs_control_state"}, callback)

        self.assertEqual(len(bridge._outbox), 0)
        callback.assert_called_once()
        self.assertEqual(callback.call_args.args[0]["error"], "connection_not_ready")

    def test_hello_is_allowed_while_connecting(self):
        bridge = make_bridge("connecting")

        bridge._send_async({"event": "hello"})

        self.assertEqual(len(bridge._outbox), 1)
        self.assertEqual(bridge._outbox[0]["payload"]["event"], "hello")

    def test_empty_pipe_response_is_a_disconnect_not_a_protocol_error(self):
        bridge = make_bridge("connected")
        bridge._translator = None
        bridge._status_lock = threading.Lock()
        bridge._last_state_message = None
        bridge.consecutive_failures = 0
        bridge.last_seen = 0.0
        bridge._set_state = Mock(wraps=bridge._set_state)
        pipe = Mock()
        pipe.__enter__ = Mock(return_value=pipe)
        pipe.__exit__ = Mock(return_value=False)
        pipe.read.return_value = b""

        with patch("builtins.open", return_value=pipe):
            response = bridge._send({"event": "hello", "request_id": "test"})

        self.assertEqual(response["error"], "transport_error")
        self.assertEqual(bridge.connection_state, "disconnected")
        state_messages = [call.args[0] for call in bridge._set_state.call_args_list]
        self.assertNotIn("incompatible", state_messages)

    def test_automatic_setup_keeps_loading_state_quiet(self):
        bridge = make_bridge("connected")
        bridge._translator = None
        bridge._status_lock = threading.Lock()
        bridge.consecutive_failures = 0
        bridge.last_seen = 0.0
        bridge._set_state = Mock()
        response = {
            "ok": False,
            "error": "operation_not_ready",
            "request_id": "test",
            "version": 3,
        }
        pipe = Mock()
        pipe.__enter__ = Mock(return_value=pipe)
        pipe.__exit__ = Mock(return_value=False)
        pipe.read.return_value = __import__("json").dumps(response).encode("utf-8")

        with patch("builtins.open", return_value=pipe):
            result = bridge._send(
                {"event": "setup_scenes", "request_id": "test"},
                quiet_not_ready=True,
            )

        self.assertEqual(result["error"], "operation_not_ready")
        bridge._set_state.assert_not_called()

    def test_missing_streamdeck_target_does_not_degrade_connection(self):
        bridge = make_bridge("connected")
        bridge._translator = None
        bridge._status_lock = threading.Lock()
        bridge.consecutive_failures = 0
        bridge.last_seen = 0.0
        bridge._set_state = Mock()
        response = {
            "ok": False,
            "error": "operation_not_ready",
            "request_id": "test",
            "version": 3,
        }
        pipe = Mock()
        pipe.__enter__ = Mock(return_value=pipe)
        pipe.__exit__ = Mock(return_value=False)
        pipe.read.return_value = __import__("json").dumps(response).encode("utf-8")

        with patch("builtins.open", return_value=pipe):
            result = bridge._send({
                "event": "obs_control_state", "request_id": "test",
            })

        self.assertEqual(result["error"], "operation_not_ready")
        self.assertEqual(bridge.connection_state, "connected")
        bridge._set_state.assert_not_called()
        bridge._record.assert_not_called()
        self.assertGreater(bridge.last_seen, 0.0)

    def test_configuration_error_is_reported_without_breaking_transport(self):
        bridge = make_bridge("connected")
        bridge._translator = None
        bridge._status_lock = threading.Lock()
        bridge.consecutive_failures = 0
        bridge.last_seen = 0.0
        bridge._set_state = Mock()
        response = {
            "ok": False,
            "error": "operation_not_ready",
            "request_id": "test",
            "version": 3,
        }
        pipe = Mock()
        pipe.__enter__ = Mock(return_value=pipe)
        pipe.__exit__ = Mock(return_value=False)
        pipe.read.return_value = __import__("json").dumps(response).encode("utf-8")

        with patch("builtins.open", return_value=pipe):
            bridge._send({"event": "setup_scenes", "request_id": "test"})

        self.assertEqual(bridge.connection_state, "connected")
        bridge._set_state.assert_not_called()
        bridge._record.assert_called_once()

    def test_identical_background_team_sync_is_a_true_noop(self):
        bridge = make_bridge("connected")
        bridge._revision = 12
        bridge._last_sync_signature = "unchanged"
        bridge._ready_accounts = Mock(return_value=[{
            "client_id": "1-2", "account": "Test", "hwnd": 2, "engine": "unity",
        }])
        bridge._profile_payload = Mock(return_value={"game_scene": "Jeu_Dofus_Unity"})
        bridge._sync_signature = Mock(return_value="unchanged")
        bridge.setup_scenes = Mock()
        bridge._send_async = Mock()

        bridge.synchronize_team([{"name": "Test", "hwnd": 2}])

        bridge.setup_scenes.assert_not_called()
        bridge._send_async.assert_not_called()
        bridge._record.assert_not_called()
        self.assertEqual(bridge._revision, 12)


if __name__ == "__main__":
    unittest.main()
