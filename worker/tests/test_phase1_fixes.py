"""
Unit and integration tests for Phase 1 bug fixes in Growcord Selfbot.
Tests cover:
1. Navigation fallback _press_kembali in core/bot.py and autofarm.py
2. Modal max_length string character length validation in core/bot.py
3. Remaining gems estimation without double deduction in tasks/buy_wl.py
4. Lucky Clover bypass logic (clover_checked flag) in tasks/buffs.py
5. Disabled Farm button retry backoff in tasks/autofarm.py and autofarm.py
6. Anti-AFK humanized delay in core/bot.py
"""

import os
import re
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as cfg
cfg.TOKEN = "fake"
cfg.CHANNEL_ID = "200"
cfg.GROWCORD_APP_ID = "500"

from core.bot import Engine as CoreEngine, NavError
import autofarm as single_script
from tasks import buffs, buy_wl
from tasks import autofarm as task_autofarm


def make_test_msg(msg_id, text, buttons=None, author_id="500"):
    return {
        "id": str(msg_id),
        "channel_id": "200",
        "author": {"id": author_id, "name": "Growcord", "username": "Growcord", "bot": True},
        "content": "",
        "embeds": [{"title": "", "description": text}],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "label": label,
                        "custom_id": cid,
                        "disabled": disabled,
                    }
                    for cid, label, disabled in (buttons or [])
                ],
            }
        ],
    }


class TestNavigationFallback(unittest.TestCase):
    def test_core_bot_press_kembali_matches_arrow_item(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200", "1")
        doc = make_test_msg(
            101,
            "## Item • Consumables",
            [
                ("btn_select", "Select Item", False),
                ("btn_use", "🍴 Use", False),
                ("btn_back", "← Item", False),
                ("btn_custom", "Custom Item", False),
            ],
        )
        engine._session_msgs = [doc]
        engine._click = MagicMock(return_value=True)

        res = engine._press_kembali()
        self.assertTrue(res)
        engine._click.assert_called_once()
        clicked_btn = engine._click.call_args[0][1]
        self.assertEqual(clicked_btn["label"], "← Item")
        self.assertEqual(clicked_btn["custom_id"], "btn_back")

    def test_core_bot_press_kembali_variations(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200", "1")
        for label in ["Kembali", "Back", "← Items", "← Kembali", "← Back"]:
            doc = make_test_msg(102, "Layar", [("btn_1", label, False)])
            engine._session_msgs = [doc]
            engine._click = MagicMock(return_value=True)
            self.assertTrue(engine._press_kembali(), f"Failed for label: {label}")

    def test_core_bot_press_kembali_does_not_match_other_items(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200", "1")
        doc = make_test_msg(
            103,
            "Layar",
            [
                ("btn_sel", "Select Item", False),
                ("btn_codex", "Item Codex", False),
                ("btn_custom", "Custom Item", False),
            ],
        )
        engine._session_msgs = [doc]
        engine._click = MagicMock(return_value=True)
        self.assertFalse(engine._press_kembali())
        engine._click.assert_not_called()

    def test_single_script_press_kembali_matches_arrow_item(self):
        engine = single_script.Engine(MagicMock(), MagicMock(), "200", "1")
        doc = make_test_msg(
            104,
            "## Item • Consumables",
            [
                ("btn_select", "Select Item", False),
                ("btn_use", "🍴 Use", False),
                ("btn_back", "← Item", False),
            ],
        )
        engine._session_msgs = [doc]
        engine._click = MagicMock(return_value=True)

        res = engine._press_kembali()
        self.assertTrue(res)
        engine._click.assert_called_once()
        clicked_btn = engine._click.call_args[0][1]
        self.assertEqual(clicked_btn["label"], "← Item")

    def test_core_bot_press_kembali_handles_disabled_button_gracefully(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "200", "1")
        doc = make_test_msg(105, "Layar", [("btn_1", "Kembali", True)])
        engine._session_msgs = [doc]
        # Must catch NavError on disabled button and return False instead of crashing
        self.assertFalse(engine._press_kembali())

    def test_single_script_press_kembali_handles_disabled_button_gracefully(self):
        engine = single_script.Engine(MagicMock(), MagicMock(), "200", "1")
        doc = make_test_msg(106, "Layar", [("btn_1", "← Item", True)])
        engine._session_msgs = [doc]
        self.assertFalse(engine._press_kembali())


class TestModalMaxLength(unittest.TestCase):
    def test_modal_max_length_preserves_valid_digits(self):
        api = MagicMock()
        gw = MagicMock()
        engine = CoreEngine(api, gw, "200", "1")
        engine.msg = make_test_msg(201, "Locks Toko", [("btn_beli_wl", "Beli WL", False)])
        engine.click_screen_button = MagicMock()
        # Modal dengan max_length: 3 (max 3 digit karakter string)
        engine.capture_modal = MagicMock(
            return_value={
                "custom_id": "modal_wl",
                "id": "m1",
                "field_id": "jumlah",
                "max_length": "3",
                "token": "tok1",
            }
        )
        # amount 100 has 3 characters -> should NOT be truncated to 3!
        result = engine.buy_with_form("locks", "beli_wl", 100)
        self.assertEqual(result, 100)
        api.submit_modal.assert_called_once_with(
            engine.msg,
            "modal_wl",
            [("jumlah", 100)],
            "1",
            interaction_token="tok1",
            modal_id="m1",
        )

    def test_modal_max_length_clamps_when_digits_exceed(self):
        api = MagicMock()
        gw = MagicMock()
        engine = CoreEngine(api, gw, "200", "1")
        engine.msg = make_test_msg(202, "Locks Toko", [("btn_beli_wl", "Beli WL", False)])
        engine.click_screen_button = MagicMock()
        # Modal dengan max_length: 3, tapi amount = 1000 (4 digit)
        engine.capture_modal = MagicMock(
            return_value={
                "custom_id": "modal_wl",
                "id": "m2",
                "field_id": "jumlah",
                "max_length": 3,
                "token": "tok2",
            }
        )
        result = engine.buy_with_form("locks", "beli_wl", 1000)
        self.assertEqual(result, 999)
        api.submit_modal.assert_called_once_with(
            engine.msg,
            "modal_wl",
            [("jumlah", 999)],
            "1",
            interaction_token="tok2",
            modal_id="m2",
        )

    def test_modal_string_amount_converted_safely(self):
        api = MagicMock()
        gw = MagicMock()
        engine = CoreEngine(api, gw, "200", "1")
        engine.msg = make_test_msg(203, "Locks Toko", [("btn_beli_wl", "Beli WL", False)])
        engine.click_screen_button = MagicMock()
        engine.capture_modal = MagicMock(
            return_value={
                "custom_id": "modal_wl",
                "id": "m3",
                "field_id": "jumlah",
                "max_length": 3,
                "token": "tok3",
            }
        )
        result = engine.buy_with_form("locks", "beli_wl", "50")
        self.assertEqual(result, 50)
        api.submit_modal.assert_called_once_with(
            engine.msg,
            "modal_wl",
            [("jumlah", 50)],
            "1",
            interaction_token="tok3",
            modal_id="m3",
        )


class TestBuyWLGemsEstimation(unittest.TestCase):
    def test_no_double_deduction_when_reply_contains_actual_gems(self):
        api = MagicMock()
        gw = MagicMock()
        engine = CoreEngine(api, gw, "200", "1")

        # Initial state: 250,000 gems on locks screen
        locks_msg = make_test_msg(301, "Locks Toko\nGems: 250.000")
        engine.goto = MagicMock(return_value=(MagicMock(id="locks"), locks_msg))
        engine.read_gems = MagicMock(side_effect=[
            250_000,    # initial read from locks screen
            50_000,     # read from reply after cycle 1 (bought 100 WL * 2000 = 200k spent)
            2_000,      # read from reply after cycle 2 (bought 24 WL * 2000 = 48k spent)
        ])
        engine.buy_with_form = MagicMock()
        reply1 = make_test_msg(302, "Pembelian 100 WL berhasil!\nGems: 50.000")
        reply2 = make_test_msg(303, "Pembelian 24 WL berhasil!\nGems: 2.000")
        engine.wait_bot_reply = MagicMock(side_effect=[reply1, reply2])
        engine.message_text = MagicMock(side_effect=[
            "Pembelian 100 WL berhasil!\nGems: 50.000",
            "Pembelian 24 WL berhasil!\nGems: 2.000",
        ])
        engine.abort_reason = MagicMock(return_value=None)
        engine.sleep_min_max = MagicMock()

        with patch.object(buy_wl.log, "info") as mock_info:
            buy_wl.run(engine, {})
            # Verify the info calls for cycle logs
            cycle_calls = [
                call.args for call in mock_info.call_args_list
                if len(call.args) >= 7 and "siklus %d/%d" in str(call.args[0])
            ]
            self.assertEqual(len(cycle_calls), 2)
            # Cycle 1: quantity=100, bought=100, budget=124, estimate="50.000"
            self.assertEqual(cycle_calls[0][1], 1)
            self.assertEqual(cycle_calls[0][3], 100)
            self.assertEqual(cycle_calls[0][6], "50.000")

            # Cycle 2: quantity=24, bought=124, budget=124, estimate="2.000"
            self.assertEqual(cycle_calls[1][1], 2)
            self.assertEqual(cycle_calls[1][3], 24)
            self.assertEqual(cycle_calls[1][6], "2.000")


class TestLuckyCloverBypass(unittest.TestCase):
    def test_buffs_skips_clover_when_clover_checked_is_true_and_inactive(self):
        engine = MagicMock()
        engine.read_active_buffs = MagicMock(return_value={})
        engine.goto = MagicMock()
        engine.clover_checked = True

        with patch("tasks.buffs._have_item", return_value=False) as mock_have:
            with patch("tasks.buffs._use_once") as mock_use:
                with patch.object(buffs.log, "info") as mock_info:
                    # Let's run with only clover in ITEMS to test isolation
                    with patch("tasks.buffs.ITEMS", [{"slug": "clover", "nama": "Lucky Clover", "beli": None}]):
                        buffs.run(engine, {})

                        # _have_item should NOT have been called because clover was bypassed!
                        mock_have.assert_not_called()
                        mock_use.assert_not_called()
                        # Verify skip log was produced
                        skipped_logs = [call.args for call in mock_info.call_args_list if "tidak aktif dan tidak dijual di Toko, lewati" in str(call)]
                        self.assertEqual(len(skipped_logs), 1)

    def test_buffs_checks_clover_when_clover_checked_is_false(self):
        engine = MagicMock()
        engine.read_active_buffs = MagicMock(return_value={})
        engine.goto = MagicMock()
        engine.clover_checked = False

        with patch("tasks.buffs._have_item", return_value=False) as mock_have:
            with patch("tasks.buffs.ITEMS", [{"slug": "clover", "nama": "Lucky Clover", "beli": None}]):
                buffs.run(engine, {})
                # _have_item SHOULD have been called to check inventory
                mock_have.assert_called_once_with(engine, "Lucky Clover")
                # Once checked and missing, engine.clover_checked MUST be True so next cycles skip it
                self.assertTrue(engine.clover_checked)


class TestDisabledFarmButtonRetryBackoff(unittest.TestCase):
    def test_task_autofarm_retry_backoff_on_disabled_button(self):
        engine = MagicMock()
        home_msg = make_test_msg(401, "## Growcord Farm\nAuto Farm: **OFF**")
        engine.read_autofarm_state = MagicMock(side_effect=[
            "OFF",   # initial check
            "OFF",   # attempt 1 home check
            "OFF",   # attempt 2 home check
            "ON",    # attempt 2 locate fresh check -> success!
        ])
        engine.goto = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.locate = MagicMock(return_value=(MagicMock(id="home"), home_msg))

        # First click raises disabled NavError, second click succeeds
        engine.click_screen_button = MagicMock(side_effect=[
            NavError('Tombol "Farm" disabled (cooldown / tidak tersedia).'),
            None,
        ])

        with patch("time.sleep") as mock_sleep:
            task_autofarm._set_autofarm_state(engine, "ON")

            # Verify it retried
            self.assertEqual(engine.click_screen_button.call_count, 2)
            # Verify sleep was called with backoff ~3.5s
            mock_sleep.assert_any_call(3.5)

    def test_single_script_retry_backoff_on_disabled_button(self):
        engine = MagicMock()
        home_msg = make_test_msg(402, "## Growcord Farm\nAuto Farm: **OFF**")
        engine.read_autofarm_state = MagicMock(side_effect=[
            "OFF",   # initial check
            "OFF",   # attempt 1
            "OFF",   # attempt 2
            "ON",    # attempt 2 success
        ])
        engine.goto = MagicMock(return_value=(MagicMock(id="home"), home_msg))
        engine.locate = MagicMock(return_value=(MagicMock(id="home"), home_msg))

        engine.click_screen_button = MagicMock(side_effect=[
            single_script.NavError('Tombol "Farm" disabled (cooldown / tidak tersedia).'),
            None,
        ])

        with patch("time.sleep") as mock_sleep:
            single_script.set_autofarm_state(engine, "ON")
            self.assertEqual(engine.click_screen_button.call_count, 2)
            mock_sleep.assert_any_call(3.5)


class TestAntiAFKHumanDelay(unittest.TestCase):
    def test_core_bot_handle_anti_afk_includes_humanized_delay(self):
        cfg.DELAY_ANTI_AFK = (1.2, 2.2)
        api = MagicMock()
        gw = MagicMock()
        engine = CoreEngine(api, gw, "200", "1")
        afk_msg = make_test_msg(
            501,
            "@User, are you still there?",
            [("gc:keep_farm", "Yes, keep farming", False)],
        )

        with patch("time.sleep") as mock_sleep:
            res = engine.handle_anti_afk(afk_msg)
            self.assertTrue(res)
            # time.sleep must be called with a duration between 1.2 and 2.2
            mock_sleep.assert_called_once()
            delay = mock_sleep.call_args[0][0]
            self.assertGreaterEqual(delay, 1.2)
            self.assertLessEqual(delay, 2.2)
            api.click_button.assert_called_once_with(afk_msg, "gc:keep_farm", "1")


if __name__ == "__main__":
    unittest.main()
