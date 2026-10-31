import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from autofarm import BUFF_ITEMS, check_and_apply_buffs
from bot_worker import BotWorker, parse_duration_to_sec


class TestAutoRebuff(unittest.TestCase):
    def test_parse_duration_to_sec(self):
        self.assertEqual(parse_duration_to_sec("30m"), 1800)
        self.assertEqual(parse_duration_to_sec("29m 30s"), 1770)
        self.assertEqual(parse_duration_to_sec("1h 10m"), 4200)
        self.assertEqual(parse_duration_to_sec(0), 0)
        self.assertEqual(parse_duration_to_sec(None), 0)

    def test_update_buff_cache_zeroes_expired_buffs(self):
        worker = BotWorker(
            account_id="acc-test",
            label="test",
            token="dummy_token",
            channel_id="123",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        worker.last_buff_arroz = 1200
        worker.last_buff_benedict = 600
        worker.last_buff_clover = 300

        # When Growcord Farm embed shows only Arroz Con Pollo
        embed_text = "Growcord Farm\nAuto Farm: ON\nBuff Aktif:\n- Arroz Con Pollo • 25m\n"
        buffs = {"Arroz Con Pollo": 1500}
        worker._update_buff_cache(buffs, embed_text)

        self.assertEqual(worker.last_buff_arroz, 1500)
        # Benedict and Clover were missing from "Buff Aktif", so they must be 0
        self.assertEqual(worker.last_buff_benedict, 0)
        self.assertEqual(worker.last_buff_clover, 0)

    def test_update_buff_cache_all_expired_when_no_buff_header(self):
        worker = BotWorker(
            account_id="acc-test",
            label="test",
            token="dummy_token",
            channel_id="123",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        worker.last_buff_arroz = 1200
        worker.last_buff_benedict = 600
        worker.last_buff_clover = 300

        # When Growcord Farm embed has no Buff Aktif header at all
        embed_text = "Growcord Farm\nAuto Farm: ON\nFarmable: Diamond Ore (1,000 Block)\n"
        buffs = {}
        worker._update_buff_cache(buffs, embed_text)

        self.assertEqual(worker.last_buff_arroz, 0)
        self.assertEqual(worker.last_buff_benedict, 0)
        self.assertEqual(worker.last_buff_clover, 0)

    @patch("bot_worker.check_and_apply_buffs")
    @patch("bot_worker.set_autofarm_state")
    def test_check_and_trigger_rebuff_specific(self, mock_set_state, mock_apply_buffs):
        mock_apply_buffs.return_value = ["Eggs Benedict"]
        worker = BotWorker(
            account_id="acc-test",
            label="test",
            token="dummy_token",
            channel_id="123",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        worker.engine = MagicMock()
        worker.last_buff_arroz = 1200 # Still running
        worker.last_buff_benedict = 0  # EXPIRED!
        worker.last_buff_clover = 600 # Still running

        worker._check_and_trigger_rebuff()

        # Should only request rebuff for Eggs Benedict!
        mock_apply_buffs.assert_called_once_with(
            worker.engine,
            target_buffs=["Eggs Benedict"],
            gem_floor=worker.gem_floor,
            current_gems=worker.last_gems,
        )
        worker.engine.goto.assert_called_with("home")
        mock_set_state.assert_called_with(worker.engine, "ON")

    @patch("bot_worker.check_and_apply_buffs")
    @patch("bot_worker.set_autofarm_state")
    def test_check_and_trigger_rebuff_batch_multiple(self, mock_set_state, mock_apply_buffs):
        mock_apply_buffs.return_value = ["Arroz Con Pollo", "Eggs Benedict"]
        worker = BotWorker(
            account_id="acc-test",
            label="test",
            token="dummy_token",
            channel_id="123",
            supabase=MagicMock(),
            notifier=MagicMock(),
        )
        worker.engine = MagicMock()
        worker.engine.clover_has_more = False # Clover exhausted, ignore
        worker.last_buff_arroz = 0     # EXPIRED!
        worker.last_buff_benedict = 0  # EXPIRED!
        worker.last_buff_clover = 0

        worker._check_and_trigger_rebuff()

        # Both Arroz & Benedict passed in unified list
        mock_apply_buffs.assert_called_once_with(
            worker.engine,
            target_buffs=["Arroz Con Pollo", "Eggs Benedict"],
            gem_floor=worker.gem_floor,
            current_gems=worker.last_gems,
        )


if __name__ == "__main__":
    unittest.main()
