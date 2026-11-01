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

    def test_capture_modal_without_channel_id(self):
        from autofarm import Engine
        engine = Engine(MagicMock(), MagicMock(), "1565409104695009413")
        # Simulasikan gateway mengirim INTERACTION_MODAL_CREATE tanpa channel_id
        modal_event = (
            "interaction",
            {
                "id": "inter-123",
                "token": "valid_token_xyz",
                "data": {
                    "custom_id": "gc:modal:benedict",
                    "components": [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 4,
                                    "custom_id": "amount",
                                    "max_length": 1,
                                }
                            ]
                        }
                    ]
                }
            },
            time.time()
        )
        engine.gw.pop_event.side_effect = [modal_event, None]
        modal = engine.capture_modal(1.0)
        self.assertIsNotNone(modal)
        self.assertEqual(modal["token"], "valid_token_xyz")
        self.assertEqual(modal["custom_id"], "gc:modal:benedict")
        self.assertEqual(modal["field_id"], "amount")

    def test_submit_modal_helper_without_token_submits_successfully(self):
        from autofarm import Engine
        engine = Engine(MagicMock(), MagicMock(), "1565409104695009413")
        engine.msg = {"id": "msg-123", "channel_id": "1565409104695009413"}
        # Modal user Discord tanpa token tetap disubmit menggunakan session_id dan modal id
        real_modal = {
            "custom_id": "gc:modal:benedict",
            "field_id": "amount",
            "id": "123456",
            "token": "",
            "application_id": "1198203414694338671",
        }
        res = engine.submit_modal_helper(real_modal, 5)
        engine.api.submit_modal.assert_called_once_with(
            engine.msg,
            "gc:modal:benedict",
            [("amount", 5)],
            engine.guild_id,
            interaction_token="",
            modal_id="123456",
            application_id="1198203414694338671",
        )

    def test_have_inventory_item_flexible_matching(self):
        from autofarm import have_inventory_item
        engine = MagicMock()
        mock_screen = MagicMock()
        mock_screen.pattern.return_value = "select_item"
        engine.goto.return_value = (mock_screen, {"id": "123"})
        engine._match_button.return_value = {"custom_id": "item_select"}

        # Kasus 1: Dropdown label 'Eggs Benedict'
        engine._select_options.return_value = [{"label": "Eggs Benedict", "value": "benedict"}]
        self.assertTrue(have_inventory_item(engine, "Eggs Benedict"))

        # Kasus 2: Dropdown label '🥚 Benedict' atau 'Benedict'
        engine._select_options.return_value = [{"label": "🥚 Benedict", "value": "benedict"}]
        self.assertTrue(have_inventory_item(engine, "Eggs Benedict"))

        # Kasus 3: Dropdown label 'Arroz Con Pollo' atau 'Arroz'
        engine._select_options.return_value = [{"label": "🍗 Arroz", "value": "arroz"}]
        self.assertTrue(have_inventory_item(engine, "Arroz Con Pollo"))


if __name__ == "__main__":
    unittest.main()
