"""
Unit and integration tests for 24/7 Deep Robustness & Anti-Regression fixes.
Verifies:
1. KeyboardInterrupt propagation (Ctrl+C cleanly stops both main supervisor and sub-loops).
2. Gateway cross-channel event isolation and filtering (no event cross-talk from other channels).
3. Gateway bounded event queue (bounds memory to maxsize, preventing OOM leaks).
4. Gateway sequence number reset on connect (prevents opcode 9 invalid session).
5. Heartbeat thread clean exit (no thread leaks across reconnects).
6. Api.request HTTP 5xx server error exponential backoff and retry.
7. Standby monitoring loop halts on Gateway fatal=True with AuthError.
8. _set_autofarm_state handles None state cleanly without raising NavError.
9. ApiError resilience in button clicks and buff purchases.
"""

import json
import os
import queue
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as cfg
cfg.TOKEN = "fake_token"
cfg.CHANNEL_ID = "200"
cfg.GROWCORD_APP_ID = "500"
cfg.DELAY_ANTI_AFK = (0.001, 0.002)

import autofarm as single_script
from core.api import Api as CoreApi, ApiError, AuthError
from core.bot import Engine as CoreEngine, NavError as CoreNavError
from core.gateway import Gateway as CoreGateway
from tasks import autofarm as task_autofarm, buffs


def make_doc(msg_id, channel_id="200", text="## Growcord Farm", buttons=None):
    comps = []
    if buttons:
        comps.append({
            "type": 1,
            "components": [
                {"type": 2, "label": lbl, "custom_id": cid, "disabled": False}
                for cid, lbl in buttons
            ]
        })
    return {
        "id": str(msg_id),
        "channel_id": str(channel_id),
        "author": {"id": "500", "name": "Growcord", "bot": True},
        "content": "",
        "embeds": [{"title": "", "description": text}],
        "components": comps,
    }


class TestCtrlCPropagation(unittest.TestCase):
    def test_run_autofarm_system_reraises_keyboard_interrupt(self):
        engine = MagicMock()
        engine.channel_id = "200"
        engine.gw = MagicMock()
        engine.gw.ready.is_set.return_value = True
        engine.gw.pop_event.side_effect = KeyboardInterrupt("Ctrl+C pressed by user")

        with patch("autofarm.prepare_autofarm"):
            with self.assertRaises(KeyboardInterrupt):
                single_script.run_autofarm_system(engine)

    def test_task_autofarm_reraises_keyboard_interrupt(self):
        engine = MagicMock()
        engine.channel_id = "200"
        engine.gw = MagicMock()
        engine.gw.ready.is_set.return_value = True
        engine.gw.pop_event.side_effect = KeyboardInterrupt("Ctrl+C pressed by user")

        with patch("tasks.autofarm._prepare_autofarm"):
            with self.assertRaises(KeyboardInterrupt):
                task_autofarm._full_autofarm_loop(engine, {})


class TestCrossChannelIsolation(unittest.TestCase):
    def test_gateway_filters_foreign_channel_messages(self):
        gw = CoreGateway("fake_token")
        gw.channel_id = "200"

        # Event in target channel 200
        gw._handle({
            "op": 0, "t": "MESSAGE_CREATE",
            "d": {"id": "1", "channel_id": "200", "content": "in channel"}
        })
        self.assertEqual(gw.events.qsize(), 1)

        # Event in foreign channel 999
        gw._handle({
            "op": 0, "t": "MESSAGE_CREATE",
            "d": {"id": "2", "channel_id": "999", "content": "other channel"}
        })
        # Should be dropped, queue size still 1
        self.assertEqual(gw.events.qsize(), 1)
        item = gw.pop_event(timeout=0.1)
        self.assertEqual(item[1]["id"], "1")

    def test_single_script_gateway_filters_foreign_channel_messages(self):
        gw = single_script.Gateway("fake_token")
        gw.channel_id = "200"

        gw._handle({
            "op": 0, "t": "MESSAGE_CREATE",
            "d": {"id": "10", "channel_id": "200", "content": "valid"}
        })
        gw._handle({
            "op": 0, "t": "MESSAGE_CREATE",
            "d": {"id": "20", "channel_id": "999", "content": "foreign"}
        })
        self.assertEqual(gw.events.qsize(), 1)

    def test_is_anti_afk_prompt_rejects_foreign_channel(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200")
        # Anti-afk prompt in channel 200 -> True
        valid_msg = make_doc(1, channel_id="200", text="@evils_games, are you still there?", buttons=[("gc:yes", "Yes, keep farming")])
        self.assertTrue(engine.is_anti_afk_prompt(valid_msg))

        # Same anti-afk prompt in foreign channel 888 -> False
        foreign_msg = make_doc(2, channel_id="888", text="@other_user, are you still there?", buttons=[("gc:yes", "Yes, keep farming")])
        self.assertFalse(engine.is_anti_afk_prompt(foreign_msg))


class TestGatewayQueueBounding(unittest.TestCase):
    def test_gateway_bounded_queue_drops_oldest_on_overflow(self):
        gw = CoreGateway("fake_token")
        gw.events = queue.Queue(maxsize=3)
        gw.channel_id = ""

        for i in range(5):
            gw._handle({
                "op": 0, "t": "MESSAGE_CREATE",
                "d": {"id": str(i), "channel_id": "200", "content": f"msg {i}"}
            })

        self.assertEqual(gw.events.qsize(), 3)
        # Oldest (0, 1) were dropped; remaining are 2, 3, 4
        ids = [gw.pop_event(timeout=0.1)[1]["id"] for _ in range(3)]
        self.assertEqual(ids, ["2", "3", "4"])


class TestGatewayConnectionLifecycle(unittest.TestCase):
    def test_sequence_reset_to_none_on_connect(self):
        gw = CoreGateway("fake_token")
        gw.seq = 99999

        # Simulate _connect initializing sequence to None before handshake
        with patch("websocket.create_connection") as mock_ws_create:
            mock_ws = MagicMock()
            mock_ws_create.return_value = mock_ws
            # Simulate HELLO response
            gw._recv_json = MagicMock(side_effect=[
                {"op": 10, "d": {"heartbeat_interval": 45000}},
                None,
            ])
            try:
                gw._connect()
            except Exception:
                pass
            # Sequence must have been reset to None for new session
            self.assertIsNone(gw.seq)

    def test_heartbeat_stops_cleanly_via_event(self):
        gw = CoreGateway("fake_token")
        stop_event = threading.Event()
        mock_ws = MagicMock()

        thread = threading.Thread(
            target=gw._heartbeat, args=(mock_ws, 5.0, stop_event), daemon=True
        )
        thread.start()
        time.sleep(0.05)
        self.assertTrue(thread.is_alive())

        # Signal stop event
        stop_event.set()
        thread.join(timeout=0.5)
        self.assertFalse(thread.is_alive(), "Heartbeat thread did not terminate after stop_event.set()")


class TestApiServerErrorsRetry(unittest.TestCase):
    @patch("requests.Session.request")
    def test_request_retries_on_502_and_succeeds(self, mock_request):
        api = CoreApi("fake_token", "agent")

        resp_502 = MagicMock()
        resp_502.status_code = 502
        resp_502.text = "Bad Gateway"

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.content = b'{"success": true}'
        resp_200.json.return_value = {"success": True}

        mock_request.side_effect = [resp_502, resp_200]

        with patch("time.sleep"):
            data = api.request("GET", "/test_endpoint")
            self.assertEqual(data, {"success": True})
            self.assertEqual(mock_request.call_count, 2)


class TestStandbyMonitoringFatalDetection(unittest.TestCase):
    def test_standby_loop_halts_immediately_on_gateway_fatal(self):
        engine = MagicMock()
        engine.channel_id = "200"
        engine.gw = MagicMock()
        engine.gw.fatal = True
        engine.gw.ready.is_set.return_value = True
        engine.gw.pop_event.return_value = None

        with patch("tasks.autofarm._prepare_autofarm"):
            with self.assertRaises(AuthError) as ctx:
                task_autofarm._full_autofarm_loop(engine, {})
            self.assertIn("token ditolak", str(ctx.exception).lower())

    def test_single_script_standby_loop_halts_immediately_on_gateway_fatal(self):
        engine = MagicMock()
        engine.channel_id = "200"
        engine.gw = MagicMock()
        engine.gw.fatal = True
        engine.gw.ready.is_set.return_value = True
        engine.gw.pop_event.return_value = None

        with patch("autofarm.prepare_autofarm"):
            with self.assertRaises((AuthError, single_script.AuthError)) as ctx:
                single_script.run_autofarm_system(engine)
            self.assertIn("token ditolak", str(ctx.exception).lower())


class TestAutofarmStateNoneResilience(unittest.TestCase):
    def test_set_autofarm_state_returns_false_when_state_unreadable(self):
        engine = MagicMock()
        engine.goto.return_value = (MagicMock(), make_doc(1, text="Garbled message"))
        engine.read_autofarm_state.return_value = None

        # Must return False rather than raising NavError
        result = task_autofarm._set_autofarm_state(engine, "ON")
        self.assertFalse(result)

    def test_set_autofarm_state_survives_api_error_on_button(self):
        engine = MagicMock()
        home_doc = make_doc(1, text="## Growcord Farm\nAuto Farm: **OFF**")
        engine.goto.return_value = (MagicMock(), home_doc)
        engine.locate.return_value = (MagicMock(), home_doc)
        engine.read_autofarm_state.return_value = "OFF"
        engine.click_screen_button.side_effect = ApiError("HTTP 400: Component validation failed")

        with patch("time.sleep"):
            result = task_autofarm._set_autofarm_state(engine, "ON")
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
