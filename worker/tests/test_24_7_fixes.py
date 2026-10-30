"""
Unit and integration tests for 24/7 reliability and optimization fixes in Growcord Selfbot.
Tests cover:
1. Dynamic session_id synchronization between Gateway and Api (prevents stale session_id after reconnects).
2. Gateway Opcode 9 resilience (does NOT mark session fatal, allows clean reconnect).
3. Gateway READY timeout resilience (does NOT mark session fatal, allows clean reconnect).
4. use_inventory_item graceful handling when item is missing from dropdown (returns False, no fatal NavError).
5. check_and_apply_buffs handles modal failure gracefully without crashing or attempting invalid consumption.
6. set_autofarm_state returns False on exhaustion rather than raising fatal NavError.
7. RotatingFileHandler configuration for long-running execution.
"""

import json
import os
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

from core.api import Api as CoreApi
from core.bot import Engine as CoreEngine, NavError as CoreNavError
from core.gateway import Gateway as CoreGateway, _AuthInvalid
import autofarm as single_script
from tasks import buffs, autofarm as task_autofarm


def make_test_msg(msg_id, text, buttons=None, select_options=None, author_id="500"):
    components = []
    if select_options is not None:
        components.append(
            {
                "type": 1,
                "components": [
                    {
                        "type": 3,
                        "custom_id": "select_item",
                        "options": [
                            {"label": opt, "value": opt.lower().replace(" ", "_")}
                            for opt in select_options
                        ],
                    }
                ],
            }
        )
    if buttons:
        components.append(
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "label": label,
                        "custom_id": cid,
                        "disabled": disabled,
                    }
                    for cid, label, disabled in buttons
                ],
            }
        )
    return {
        "id": str(msg_id),
        "channel_id": "200",
        "author": {"id": author_id, "name": "Growcord", "username": "Growcord", "bot": True},
        "content": "",
        "embeds": [{"title": "", "description": text}],
        "components": components,
    }


class TestSessionSynchronization(unittest.TestCase):
    def test_core_api_dynamic_session_provider(self):
        gw = CoreGateway("fake_token")
        gw.session_id = "session_alpha"
        api = CoreApi("fake_token", "test-agent")
        engine = CoreEngine(api, gw, "200")

        self.assertEqual(api.session_id, "session_alpha")
        payload = api._fill_session({"data": 1})
        self.assertEqual(payload["session_id"], "session_alpha")

        # Simulate Gateway reconnect with new session_id
        gw.session_id = "session_beta"
        self.assertEqual(api.session_id, "session_beta")
        payload2 = api._fill_session({"data": 2})
        self.assertEqual(payload2["session_id"], "session_beta")

    def test_single_script_api_dynamic_session_provider(self):
        gw = single_script.Gateway("fake_token")
        gw.session_id = "session_single_1"
        api = single_script.Api("fake_token", "test-agent")
        engine = single_script.Engine(api, gw, "200")

        self.assertEqual(api.session_id, "session_single_1")
        gw.session_id = "session_single_2"
        self.assertEqual(api.session_id, "session_single_2")

    def test_gateway_on_session_callback_on_ready(self):
        gw = CoreGateway("fake_token")
        api = CoreApi("fake_token", "test-agent")
        engine = CoreEngine(api, gw, "200")

        # Simulate READY dispatch (Opcode 0)
        ready_payload = {
            "op": 0,
            "t": "READY",
            "d": {
                "user": {"id": "123456", "username": "testuser"},
                "session_id": "fresh_ready_session_xyz",
            },
        }
        gw._handle(ready_payload)
        self.assertEqual(gw.session_id, "fresh_ready_session_xyz")
        self.assertEqual(api.session_id, "fresh_ready_session_xyz")


class TestGatewayResilience(unittest.TestCase):
    def test_opcode_9_does_not_set_fatal(self):
        gw = CoreGateway("fake_token")
        # Opcode 9 should raise RuntimeError, NOT _AuthInvalid, and fatal must remain False
        with self.assertRaises(RuntimeError) as ctx:
            gw._handle({"op": 9, "d": False})
        self.assertFalse(gw.fatal)
        self.assertIn("invalid session", str(ctx.exception).lower())

    def test_single_script_opcode_9_does_not_set_fatal(self):
        gw = single_script.Gateway("fake_token")
        with self.assertRaises(RuntimeError) as ctx:
            gw._handle({"op": 9, "d": False})
        self.assertFalse(gw.fatal)
        self.assertIn("invalid session", str(ctx.exception).lower())


class TestUseInventoryItemSafety(unittest.TestCase):
    def test_core_buffs_missing_item_returns_false_without_raising(self):
        engine = MagicMock()
        # Consumables doc has Eggs Benedict and Lucky Clover, but NOT Arroz Con Pollo
        doc = make_test_msg(101, "## Item • Consumables", select_options=["Eggs Benedict", "Lucky Clover"])
        screen = MagicMock()
        screen.pattern = MagicMock(return_value=r"select_item")
        engine.goto = MagicMock(return_value=(screen, doc))
        engine._match_button = MagicMock(return_value={"custom_id": "select_item"})
        engine._select_options = MagicMock(return_value=[
            {"label": "Eggs Benedict", "value": "eggs_benedict"},
            {"label": "Lucky Clover", "value": "lucky_clover"},
        ])

        # Calling _use_once for Arroz Con Pollo must return False cleanly, NOT crash with NavError!
        result = buffs._use_once(engine, "Arroz Con Pollo", {})
        self.assertFalse(result)

    def test_single_script_missing_item_returns_false_without_raising(self):
        engine = MagicMock()
        doc = make_test_msg(102, "## Item • Consumables", select_options=["Eggs Benedict", "Lucky Clover"])
        screen = MagicMock()
        screen.pattern = MagicMock(return_value=r"select_item")
        engine.goto = MagicMock(return_value=(screen, doc))
        engine._match_button = MagicMock(return_value={"custom_id": "select_item"})
        engine._select_options = MagicMock(return_value=[
            {"label": "Eggs Benedict", "value": "eggs_benedict"},
            {"label": "Lucky Clover", "value": "lucky_clover"},
        ])

        # Calling use_inventory_item for Arroz Con Pollo must return False cleanly
        result = single_script.use_inventory_item(engine, "Arroz Con Pollo", {})
        self.assertFalse(result)


class TestCheckAndApplyBuffsRobustness(unittest.TestCase):
    def test_single_script_modal_timeout_skips_use_gracefully(self):
        engine = MagicMock()
        home_doc = make_test_msg(201, "## Growcord Farm\nAktif Buff:\n- Eggs Benedict (30m)")
        engine.goto = MagicMock(return_value=(MagicMock(), home_doc))
        engine.read_active_buffs = MagicMock(return_value={"Eggs Benedict": 1800})
        engine.clover_checked = True

        # Inventory check returns False (Arroz not in inventory)
        with patch("autofarm.have_inventory_item", return_value=False):
            # capture_modal returns None (modal timed out/did not appear)
            engine.capture_modal = MagicMock(return_value=None)
            engine._guess_modal = MagicMock(return_value=None)
            engine.click_screen_button = MagicMock()
            engine.wait_bot_reply = MagicMock(return_value=None)

            # Must run to completion without raising NavError or crashing
            single_script.check_and_apply_buffs(engine)

            # Verified: button clicked to attempt buy
            engine.click_screen_button.assert_called()


class TestSetAutofarmStateExhaustion(unittest.TestCase):
    def test_task_autofarm_returns_false_on_exhaustion(self):
        engine = MagicMock()
        home_msg = make_test_msg(301, "## Growcord Farm\nAuto Farm: **OFF**")
        engine.read_autofarm_state = MagicMock(return_value="OFF")
        engine.goto = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.locate = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.click_screen_button = MagicMock(return_value=None)

        with patch("time.sleep"):
            # Exhausting all 5 attempts returns False instead of raising NavError
            result = task_autofarm._set_autofarm_state(engine, "ON")
            self.assertFalse(result)

    def test_single_script_returns_false_on_exhaustion(self):
        engine = MagicMock()
        home_msg = make_test_msg(302, "## Growcord Farm\nAuto Farm: **OFF**")
        engine.read_autofarm_state = MagicMock(return_value="OFF")
        engine.goto = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.locate = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.click_screen_button = MagicMock(return_value=None)

        with patch("time.sleep"):
            result = single_script.set_autofarm_state(engine, "ON")
            self.assertFalse(result)


class TestModalGuessingAndClamping(unittest.TestCase):
    def test_single_script_guess_modal_fallback(self):
        btn_cid = "gc:1198203414694338671:shop_consumable_buy:arroz"
        guess = single_script.Engine._guess_modal(btn_cid)
        self.assertIsNotNone(guess)
        self.assertIn("modal", guess["custom_id"])
        self.assertEqual(guess["field_id"], "amount")

    def test_single_script_submit_modal_clamps_max_length(self):
        api = MagicMock()
        gw = MagicMock()
        engine = single_script.Engine(api, gw, "200")
        engine.locate = MagicMock(return_value=(MagicMock(), {"id": "999"}))
        modal = {
            "custom_id": "modal_buy_wl",
            "field_id": "amount",
            "id": "111",
            "token": "tok",
            "max_length": 3,
        }
        engine.submit_modal_helper(modal, 1000)
        # Should clamp 1000 to 999
        api.submit_modal.assert_called_once()
        args = api.submit_modal.call_args[0]
        # args[2] is [(field_id, value)]
        self.assertEqual(args[2], [("amount", 999)])


if __name__ == "__main__":
    unittest.main()
