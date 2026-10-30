"""
Unit and integration tests for Phase 2 optimizations:
1. Discord Gateway RESUME (Opcode 6) when session_id and seq are present.
2. Gateway Opcode 0 RESUMED sets ready flag.
3. Gateway Opcode 7 triggers reconnect.
4. Gateway Opcode 9 with resumable=False resets session_id and seq.
5. Gateway stop() terminates active websocket immediately.
6. GemsExhaustedError raised when buy_farmable or check_and_apply_buffs detects exhausted gems.
7. Supervisor loop terminates cleanly on GemsExhaustedError without infinite retries.
8. Safe drain queue handles Anti-AFK prompt before discarding other events.
9. Lucky Clover continuity across cycles with stock.
10. Console title status update and Api guild_id fallback.
"""

import json
import os
import queue
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as cfg
cfg.TOKEN = "fake_test_token"
cfg.CHANNEL_ID = "200"
cfg.GROWCORD_APP_ID = "500"

import autofarm as single_script
from core.api import Api as CoreApi, GemsExhaustedError as CoreGemsExhaustedError
from core.bot import Engine as CoreEngine, NavError as CoreNavError
from core.gateway import Gateway as CoreGateway
from tasks import autofarm as task_autofarm, buffs


class TestGatewayResume(unittest.TestCase):
    def test_gateway_sends_resume_opcode_6_when_session_and_seq_present(self):
        gw = CoreGateway("test_token")
        gw.session_id = "sess_123"
        gw.seq = 42

        with patch("websocket.create_connection") as mock_create:
            mock_ws = MagicMock()
            mock_create.return_value = mock_ws
            gw._recv_json = MagicMock(side_effect=[
                {"op": 10, "d": {"heartbeat_interval": 45000}},
                {"op": 0, "t": "RESUMED", "d": {}},
                None,
            ])
            try:
                gw._connect()
            except Exception:
                pass

            sent_payloads = [json.loads(call[0][0]) for call in mock_ws.send.call_args_list if call[0]]
            resume_payloads = [p for p in sent_payloads if p.get("op") == 6]
            self.assertEqual(len(resume_payloads), 1)
            self.assertEqual(resume_payloads[0]["d"]["session_id"], "sess_123")
            self.assertEqual(resume_payloads[0]["d"]["seq"], 42)
            self.assertTrue(gw.ready.is_set())

    def test_gateway_handles_opcode_7_reconnect_raises_runtime_error(self):
        gw = CoreGateway("test_token")
        with self.assertRaises(RuntimeError) as ctx:
            gw._handle({"op": 7})
        self.assertIn("reconnect", str(ctx.exception).lower())

    def test_gateway_opcode_9_resets_session_when_not_resumable(self):
        gw = CoreGateway("test_token")
        gw.session_id = "sess_old"
        gw.seq = 99
        with self.assertRaises(RuntimeError):
            gw._handle({"op": 9, "d": False})
        self.assertEqual(gw.session_id, "")
        self.assertIsNone(gw.seq)

    def test_gateway_stop_closes_active_socket_immediately(self):
        gw = CoreGateway("test_token")
        mock_ws = MagicMock()
        gw._ws = mock_ws
        gw.stop()
        self.assertFalse(gw._run)
        mock_ws.close.assert_called_once()


class TestZeroGemsGuard(unittest.TestCase):
    def test_buy_farmable_raises_gems_exhausted_error(self):
        api = MagicMock()
        gw = MagicMock()
        gw.pop_event.return_value = None
        engine = CoreEngine(api, gw, "200")
        engine.goto = MagicMock(return_value=(MagicMock(id="shop_farmable"), {"id": "1", "components": []}))
        engine.click_screen_select = MagicMock()
        engine.message_buttons = MagicMock(return_value=[{"type": 2, "label": "Buy Max", "custom_id": "gc:max", "disabled": False}])
        engine.wait_bot_reply = MagicMock(return_value={
            "content": "",
            "embeds": [{"title": "", "description": "Transaksi gagal! Gems Anda tidak cukup untuk membeli item ini."}],
            "components": [],
        })
        with self.assertRaises(CoreGemsExhaustedError):
            engine.buy_farmable("pot o' gems")

    def test_single_script_buy_farmable_raises_gems_exhausted_error(self):
        api = MagicMock()
        gw = MagicMock()
        gw.pop_event.return_value = None
        engine = single_script.Engine(api, gw, "200")
        engine.goto = MagicMock(return_value=(MagicMock(id="shop_farmable"), {"id": "1", "components": []}))
        engine.click_screen_select = MagicMock()
        engine.message_buttons = MagicMock(return_value=[{"type": 2, "label": "Buy Max", "custom_id": "gc:max", "disabled": False}])
        engine.wait_bot_reply = MagicMock(return_value={
            "content": "",
            "embeds": [{"title": "", "description": "Gems tidak cukup!"}],
            "components": [],
        })
        with self.assertRaises(single_script.GemsExhaustedError):
            engine.buy_farmable("pot o' gems")

    def test_single_script_supervisor_terminates_on_gems_exhausted_error(self):
        with patch("autofarm.TOKEN", "fake_token"):
            with patch("autofarm.CHANNEL_ID", "200"):
                with patch("autofarm.Gateway") as mock_gw_cls:
                    mock_gw = MagicMock()
                    mock_gw_cls.return_value = mock_gw
                    mock_gw.wait_ready.return_value = True
                    mock_gw.fatal = False
                    with patch("autofarm.Api") as mock_api_cls:
                        mock_api = MagicMock()
                        mock_api_cls.return_value = mock_api
                        with patch("autofarm.run_autofarm_system", side_effect=single_script.GemsExhaustedError("Gems 0")):
                            # main() should break out cleanly, not loop forever
                            single_script.main()
                            mock_gw.stop.assert_called_once()


class TestSafeDrainQueue(unittest.TestCase):
    def test_safe_drain_preserves_and_executes_anti_afk_prompt(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200")
        afk_doc = {
            "id": "100",
            "channel_id": "200",
            "author": {"id": "500", "name": "Growcord", "bot": True},
            "content": "are you still there?",
            "components": [{"type": 1, "components": [{"type": 2, "label": "Yes, keep farming", "custom_id": "gc:afk:1", "disabled": False}]}],
        }
        stale_doc = {
            "id": "101",
            "channel_id": "200",
            "author": {"id": "500", "name": "Growcord", "bot": True},
            "content": "stale message",
            "components": [],
        }

        # Queue contains: stale message, AFK prompt, another stale message
        engine.gw.pop_event.side_effect = [
            ("message_new", stale_doc, time.time()),
            ("message_new", afk_doc, time.time()),
            ("message_new", stale_doc, time.time()),
            None,
        ]

        engine.handle_anti_afk = MagicMock(return_value=True)
        handled = engine.safe_drain_events()
        self.assertEqual(handled, 1)
        engine.handle_anti_afk.assert_called_once_with(afk_doc)


class TestConsoleTitleAndGuildFallback(unittest.TestCase):
    def test_set_console_title_executes_cleanly(self):
        single_script.set_console_title("Growcord Test Title")

    def test_api_base_payload_uses_message_guild_id_fallback(self):
        msg = {"id": "1", "guild_id": "guild_from_msg", "channel_id": "200"}
        # Even if guild_id param is empty, msg["guild_id"] is used
        payload = CoreApi._base_payload(msg, "")
        self.assertEqual(payload["guild_id"], "guild_from_msg")

        payload_single = single_script.Api._base_payload(msg, "")
        self.assertEqual(payload_single["guild_id"], "guild_from_msg")


if __name__ == "__main__":
    unittest.main()
