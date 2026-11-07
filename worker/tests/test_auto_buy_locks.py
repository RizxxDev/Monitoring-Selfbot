import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from autofarm import (
    AUTO_LOCK_GEMS_THRESHOLD,
    GROWCORD_APP_ID,
    SOURCES as AUTOFARM_SOURCES,
    Engine as AutofarmEngine,
    prepare_autofarm,
    route_steps as autofarm_route_steps,
)
from bot_worker import BotWorker
from core.bot import Engine as CoreEngine
from core.screens import SOURCES as CORE_SOURCES, route_steps as core_route_steps


class TestAutoBuyLocks(unittest.TestCase):
    def test_threshold_default_is_2_1_billion(self):
        self.assertEqual(AUTO_LOCK_GEMS_THRESHOLD, 2_100_000_000)

    def test_route_steps_and_locks_screen_patterns(self):
        self.assertEqual(autofarm_route_steps("home", "locks"), ["toko", "locks"])
        self.assertEqual(autofarm_route_steps("locks", "home"), ["kembali", "kembali"])
        self.assertEqual(core_route_steps("home", "locks"), ["toko", "locks"])
        self.assertEqual(core_route_steps("locks", "home"), ["kembali", "kembali"])

        for sources in (AUTOFARM_SOURCES, CORE_SOURCES):
            locks_screen = sources["locks"]
            pat = locks_screen.pattern("beli_all")
            self.assertIsNotNone(pat.search("Beli All"))
            self.assertIsNotNone(pat.search("Buy All"))
            self.assertIsNotNone(pat.search("💰 Beli All"))

    def test_autofarm_engine_buy_all_locks(self):
        engine = AutofarmEngine(MagicMock(), MagicMock(), "123456789")
        locks_msg = {
            "id": "msg-locks",
            "channel_id": "123456789",
            "author": {"id": GROWCORD_APP_ID, "bot": True, "username": "Growcord"},
            "embeds": [{"title": "Locks Toko", "description": "Pembelian WL bebas pajak"}],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {"type": 2, "label": "Beli WL", "custom_id": "gc:lock:wl"},
                        {"type": 2, "label": "Beli All", "custom_id": "gc:lock:all"},
                        {"type": 2, "label": "← Kembali", "custom_id": "gc:lock:back"},
                    ],
                }
            ],
        }
        home_msg = {
            "id": "msg-home",
            "channel_id": "123456789",
            "author": {"id": GROWCORD_APP_ID, "bot": True, "username": "Growcord"},
            "embeds": [
                {
                    "title": "Growcord Farm",
                    "description": "Gems: **12,345**\nAuto Farm: **ON**",
                }
            ],
        }
        reply_msg = {
            "id": "msg-reply",
            "channel_id": "123456789",
            "author": {"id": GROWCORD_APP_ID, "bot": True, "username": "Growcord"},
            "content": "Berhasil membeli semua lock!",
        }

        engine.goto = MagicMock(side_effect=[(AUTOFARM_SOURCES["locks"], locks_msg), (AUTOFARM_SOURCES["home"], home_msg)])
        engine.click_screen_button = MagicMock()
        engine.wait_bot_reply = MagicMock(return_value=reply_msg)

        res = engine.buy_all_locks()

        self.assertTrue(res["ok"])
        self.assertEqual(res["gems_after"], 12345)
        engine.click_screen_button.assert_called_once_with("locks", "beli_all", msg=locks_msg)
        self.assertEqual([c.args[0] for c in engine.goto.call_args_list], ["locks", "home"])

    def test_core_engine_buy_all_locks(self):
        engine = CoreEngine(MagicMock(), MagicMock(), "123456789")
        locks_msg = {"id": "msg-locks", "author": {"id": GROWCORD_APP_ID, "bot": True}}
        home_msg = {
            "id": "msg-home",
            "author": {"id": GROWCORD_APP_ID, "bot": True},
            "embeds": [{"description": "Gems: 5,000\nAuto Farm: ON"}],
        }
        engine.goto = MagicMock(side_effect=[(CORE_SOURCES["locks"], locks_msg), (CORE_SOURCES["home"], home_msg)])
        engine.click_screen_button = MagicMock()
        engine.wait_bot_reply = MagicMock(return_value=None)

        res = engine.buy_all_locks()

        self.assertTrue(res["ok"])
        self.assertEqual(res["gems_after"], 5000)
        engine.click_screen_button.assert_called_once_with("locks", "beli_all", msg=locks_msg)
        self.assertEqual([c.args[0] for c in engine.goto.call_args_list], ["locks", "home"])

    @patch("bot_worker.save_account_state")
    @patch("bot_worker.check_and_apply_buffs")
    @patch("bot_worker.set_autofarm_state")
    def test_bot_worker_priority_1_executes_before_restock_and_rebuff(
        self, mock_set_state, mock_apply_buffs, mock_save_state
    ):
        supabase = MagicMock()
        notifier = MagicMock()
        worker = BotWorker(
            account_id="acc-lock-1",
            label="MainFarmer",
            token="dummy_token",
            channel_id="123456",
            farmable_item="Diamond Ore",
            supabase=supabase,
            notifier=notifier,
        )
        engine = MagicMock()
        worker.engine = engine

        embed_data = {
            "id": "msg-1",
            "channel_id": "123456",
            "author": {"id": GROWCORD_APP_ID},
        }
        # Embed memiliki Gems >= 2.1B, Stock == 0, dan Buff habis semua!
        engine.message_text.return_value = (
            "Growcord Farm\nGems: 2,105,000,000\nInventori: 0 / 20,000\nAuto Farm: ON"
        )
        engine.read_gems.return_value = 2_105_000_000
        engine.read_farmable_stock.return_value = 0
        engine.read_active_buffs.return_value = {}
        engine.buy_all_locks.return_value = {
            "ok": True,
            "gems_after": 5_000_000,
            "reply_text": "Purchased 21 BGL!",
        }
        engine.goto.return_value = ("home", {"id": "msg-home"})

        worker._process_growcord_embed(embed_data)

        # Prioritas #1: Beli All Lock dijalankan terlebih dahulu, lalu kembali ke home & set Farm ON
        engine.buy_all_locks.assert_called_once()
        engine.goto.assert_called_with("home")
        mock_set_state.assert_called_once_with(engine, "ON")
        engine.safe_drain_events.assert_called_once()

        # Restock & Rebuff TIDAK dipanggil pada tick yang sama (menghindari penundaan konversi lock)
        engine.buy_farmable.assert_not_called()
        mock_apply_buffs.assert_not_called()

        # Saldo gems diperbarui ke sisa setelah konversi lock
        self.assertEqual(worker.last_gems, 5_000_000)

        # Log Supabase (SHOP_LOCK_PURCHASE) & Discord Webhook terkirim
        supabase.log_event.assert_called_once()
        log_args = supabase.log_event.call_args[0]
        self.assertEqual(log_args[0], "acc-lock-1")
        self.assertEqual(log_args[1], "SHOP_LOCK_PURCHASE")
        self.assertEqual(log_args[2], "INFO")
        notifier.send_alert.assert_called_once()
        mock_save_state.assert_called()

    @patch("bot_worker.save_account_state")
    @patch("bot_worker.set_autofarm_state")
    def test_bot_worker_cooldown_prevents_duplicate_lock_purchase(
        self, mock_set_state, mock_save_state
    ):
        worker = BotWorker(
            account_id="acc-lock-2",
            label="CooldownTest",
            token="dummy_token",
            channel_id="123456",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        engine = MagicMock()
        engine.clover_has_more = False
        worker.engine = engine
        worker._last_lock_buy_time = time.time()  # Baru saja beli < 60s lalu

        embed_data = {"id": "msg-stale", "channel_id": "123456"}
        engine.message_text.return_value = (
            "Growcord Farm\nGems: 2,100,500,000\nBuff Aktif\n- Arroz Con Pollo • 20m\n- Eggs Benedict • 20m"
        )
        engine.read_gems.return_value = 2_100_500_000
        engine.read_farmable_stock.return_value = 15000
        engine.read_active_buffs.return_value = {"Arroz Con Pollo": 1200, "Eggs Benedict": 1200}

        worker._process_growcord_embed(embed_data)

        engine.buy_all_locks.assert_not_called()

    @patch("bot_worker.save_account_state")
    def test_bot_worker_does_not_buy_locks_below_threshold(self, mock_save_state):
        worker = BotWorker(
            account_id="acc-lock-3",
            label="BelowThreshold",
            token="dummy_token",
            channel_id="123456",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        engine = MagicMock()
        engine.clover_has_more = False
        worker.engine = engine

        embed_data = {"id": "msg-below", "channel_id": "123456"}
        engine.message_text.return_value = (
            "Growcord Farm\nGems: 2,099,999,999\nBuff Aktif\n- Arroz Con Pollo • 20m\n- Eggs Benedict • 20m"
        )
        engine.read_gems.return_value = 2_099_999_999
        engine.read_farmable_stock.return_value = 10000
        engine.read_active_buffs.return_value = {"Arroz Con Pollo": 1200, "Eggs Benedict": 1200}

        worker._process_growcord_embed(embed_data)

        engine.buy_all_locks.assert_not_called()

    def test_prepare_autofarm_triggers_buy_all_locks_at_threshold(self):
        engine = MagicMock()
        engine.clover_checked = True
        engine.clover_has_more = False
        home_before = {"id": "home-before"}
        home_after = {"id": "home-after"}
        engine.goto.side_effect = [("home", home_before), ("home", home_after)]
        engine.read_gems.return_value = 2_100_000_000
        engine.read_farmable_stock.return_value = 15000
        engine.read_active_buffs.return_value = {"Arroz Con Pollo": 1500, "Eggs Benedict": 1500}
        engine.read_autofarm_state.return_value = "ON"
        engine.fmt_int.side_effect = lambda n: f"{n:,}"

        prepare_autofarm(engine, farmable_item="Diamond Ore")

        engine.buy_all_locks.assert_called_once()


if __name__ == "__main__":
    unittest.main()
