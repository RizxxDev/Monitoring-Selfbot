"""
Self-test offline: menjalankan engine lengkap terhadap bot simulasi.
Tidak butuh token / koneksi Discord.

Jalankan: python selftest.py
"""

import os
import queue
import sys
import time

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import config as cfg  # noqa: E402

cfg.TOKEN = "fake"
cfg.CHANNEL_ID = "200"
cfg.GROWCORD_APP_ID = ""
cfg.DELAY_NAV = (0.2, 0.3)
cfg.DELAY_BUY = (0.2, 0.3)
cfg.DELAY_ANTI_AFK = (0.01, 0.02)
cfg.MODAL_TIMEOUT = 3.0
cfg.REPLY_TIMEOUT = 5.0

from core.bot import Engine  # noqa: E402
from tasks import autofarm, buffs, buy_wl  # noqa: E402
from tasks.buffs import RX_ALREADY  # noqa: E402
from tasks.watch import run as run_watch  # noqa: E402


def make_msg(msg_id, text, buttons=None, extras=None, author="Growcord", bot_flag=True):
    doc = {
        "id": str(msg_id),
        "channel_id": "200",
        "author": {"id": "500", "name": author, "username": author, "bot": bot_flag},
        "content": "",
        "embeds": [
            {
                "title": "",
                "author": {"name": "Growcord"},
                "description": text,
                "footer": {"text": ""},
            }
        ],
        "components": [
            {
                "type": 1,
                "components": [
                    {"type": 2, "label": label, "custom_id": cid}
                    for cid, label in (buttons or [])
                ],
            }
        ],
    }
    if extras:
        doc["components"] = extras + doc["components"]
    return doc


HOME = "## ?? Growcord Farm"
ITEMS = "## ?? Item • Terbatas Item\nPilih kategori item"
SHOP = "Consumables Toko\nHarga: 5 gems per unit"
TOKO = "Toko\nPilih kategori shop here"
NAMES = {
    "clover": "Lucky Clover",
    "arroz": "Arroz Con Pollo",
    "eggs_benedict": "Eggs Benedict",
}


class FakeGateway:
    user_id = "999"

    def __init__(self):
        self.events = queue.Queue()

    def pop_event(self, timeout=0.5):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def put(self, kind, data):
        self.events.put((kind, data, time.time()))


class FakeApi:
    """bot simulasi meniru Growcord:
    - satu pesan "panel" (PANEL_ID) di-edit utk setiap re-render layar
    - balasan (beli/pakai buff) dikirim sebagai pesan baru
    """

    PANEL_ID = 1

    def __init__(self):
        self.gems = 250_000
        self.autofarm = "OFF"
        self.farmable_stock = 17_447
        self.owned = {"clover": 0, "arroz": 0, "eggs_benedict": 0}
        self.selected = None
        self.active = {}
        self.current = "home"
        self.pending_itembuy = None
        self.pending_modal = False
        self.submitted = []
        self.gateway = None
        self.msgs = [self.render()]

    # ---------------- util ----------------
    def broadcast(self, data):
        kind = "message_edit" if data["id"] == str(self.PANEL_ID) else "message_new"
        self.gateway.put(kind, data)

    def _show(self):
        doc = self.render()
        for i, m in enumerate(self.msgs):
            if m["id"] == str(self.PANEL_ID):
                self.msgs[i] = doc
                break
        self.broadcast(doc)

    def reply(self, text):
        doc = make_msg(self.next_id(), text, [])
        self.msgs.insert(0, doc)
        self.broadcast(doc)

    def next_id(self):
        self._seq = getattr(self, "_seq", 10) + 1
        return self.PANEL_ID + self._seq

    def fmt_gems(self):
        return f"{self.gems:,}".replace(",", ".")

    def fmt_int(self, val):
        return f"{int(val):,}".replace(",", ".")

    # ---------------- render layar ----------------
    def render(self):
        return {
            "home": self.render_home,
            "items": self.render_items,
            "consumables": self.render_consumables,
            "toko": self.render_toko,
            "shop": self.render_shop,
            "shop_farmable": self.render_shop_farmable,
            "locks": self.render_locks,
        }[self.current](self.PANEL_ID)

    def render_home(self, mid):
        baris = [HOME, f"Auto Farm: **{self.autofarm}**"]
        if self.active:
            baris.append("Buff Aktif:")
            baris += [
                f"- {nama} • {sisa // 60}m {sisa % 60}s"
                for nama, sisa in self.active.items()
            ]
        baris.append(f"Farmable Saat Ini: 🪨 Diamond Ore ({self.fmt_int(self.farmable_stock)} Block)")
        baris.append(f"Inventori: {self.fmt_int(self.farmable_stock)} / 20.000")
        return make_msg(
            mid,
            "\n".join(baris),
            [("btn_farm", "Farm"), ("btn_toko", "Toko"), ("btn_item", "Item")],
        )

    def render_items(self, mid):
        return make_msg(
            mid, ITEMS, [("btn_cat_cons", "Consumables"), ("btn_back", "Kembali")]
        )

    def render_toko(self, mid):
        return make_msg(
            mid,
            TOKO,
            [
                ("btn_lock", "Lock"),
                ("btn_farmable", "Farmable"),
                ("btn_cons_shop", "Consumable"),
                ("btn_back", "Kembali"),
            ],
        )

    def render_shop_farmable(self, mid):
        select_row = {
            "type": 1,
            "components": [
                {
                    "type": 3,
                    "custom_id": "gc:farm_sel",
                    "placeholder": "Select Farmable",
                    "options": [
                        {
                            "label": "Pot o' Gems",
                            "value": "pot_o_gems",
                            "description": "20.000 max blocks",
                        }
                    ],
                }
            ],
        }
        return make_msg(
            mid,
            "Farmables Toko\nPilih farmable untuk dibeli",
            [("btn_buy_max", "Buy Max"), ("btn_back_toko", "Kembali")],
            extras=[select_row],
        )

    def render_shop(self, mid):
        return make_msg(
            mid,
            SHOP,
            [
                ("btn_buy_arroz", "Beli Arroz (1–5)"),
                ("btn_buy_eggs", "Beli Benedict (1–5)"),
                ("btn_back2", "Kembali"),
            ],
        )

    def render_locks(self, mid):
        return make_msg(
            mid,
            f"Locks Toko\nGems: {self.fmt_gems()} \nPembelian WL bebas pajak",
            [
                ("btn_beli_wl", "Beli WL"),
                ("btn_beli_dl", "Beli DL"),
                ("btn_back2", "Kembali"),
            ],
        )

    def render_consumables(self, mid):
        milik = [(s, NAMES[s]) for s in NAMES if self.owned.get(s, 0) > 0]
        if not milik:
            return make_msg(
                mid,
                "## ?? Item • Consumables\nNo items yet.",
                [("btn_back_item", "← Item")],
            )
        baris = ["## ?? Item • Consumables"]
        baris += [f"{nama} x{self.owned[s]}" for s, nama in milik]
        if self.selected:
            baris.append(f"Dipilih: **{NAMES[self.selected]}**")
        select_row = {
            "type": 1,
            "components": [
                {
                    "type": 3,
                    "custom_id": "gc:sel",
                    "placeholder": "Select Item",
                    "options": [
                        {
                            "label": nama,
                            "value": s,
                            "description": f"{self.owned[s]} owned",
                        }
                        for s, nama in milik
                    ],
                }
            ],
        }
        return make_msg(
            mid,
            "\n".join(baris),
            [
                ("btn_use", "🍴 Use"),
                ("btn_back_item", "← Item"),
            ],
            extras=[select_row],
        )

    # ---------------- api surface ----------------
    def channel_info(self, channel_id):
        return {"guild_id": "1", "name": "farm-rizzxgtps"}

    def get_messages(self, channel_id, limit=25):
        doc = self.render()
        for i, m in enumerate(self.msgs):
            if m["id"] == str(self.PANEL_ID):
                self.msgs[i] = doc
                break
        return list(self.msgs[:limit])

    def click_select(self, msg, custom_id, values, guild_id):
        slug = values[0]
        if custom_id == "gc:farm_sel":
            self.current = "shop_farmable"
            self._show()
            return None
        if self.owned.get(slug, 0) <= 0:
            raise RuntimeError(f"opsi {slug} tidak tersedia")
        self.selected = slug
        self.current = "consumables"
        self._show()
        return None

    def click_button(self, msg, custom_id, guild_id):
        pindah = {
            "btn_item": "items",
            "btn_toko": "toko",
            "btn_farmable": "shop_farmable",
            "btn_cons_shop": "shop",
            "btn_cat_cons": "consumables",
            "btn_lock": "locks",
            "btn_back": "home",
            "btn_back2": "toko",
            "btn_back_toko": "toko",
            "btn_back_item": "items",
        }.get(custom_id)
        if pindah:
            self.current = pindah
        if custom_id == "btn_farm":
            self.autofarm = "ON" if self.autofarm == "OFF" else "OFF"
            self.current = "home"
        elif custom_id == "btn_buy_max":
            self.farmable_stock = 20_000
            self.reply("Pembelian Pot o' Gems (Max) berhasil! Inventori: 20.000 / 20.000")
            self.current = "shop_farmable"
        elif custom_id == "btn_use":
            nama = NAMES[self.selected]
            self.owned[self.selected] -= 1
            self.selected = None
            self.active[nama] = 1800
            self.current = "consumables"
            self.reply(f"{nama} used! buff akan aktif selama 30 menit")
        elif custom_id in ("btn_buy_arroz", "btn_buy_eggs"):
            self.pending_itembuy = {
                "btn_buy_arroz": "arroz",
                "btn_buy_eggs": "eggs_benedict",
            }[custom_id]
            self.pending_modal = True
            self.gateway.put("interaction", self.modal_event(msg, "gc:itembuymodal"))
            self.current = "shop"
        elif custom_id == "btn_beli_wl":
            self.pending_modal = True
            self.gateway.put("interaction", self.modal_event(msg, "beli_wl_modal"))
            return None
        self._show()
        return None

    def modal_event(self, msg, modal_custom_id, field="jumlah"):
        return {
            "channel_id": "200",
            "token": "modal_token_" + modal_custom_id,
            "message": {"id": msg["id"]},
            "data": {
                "custom_id": modal_custom_id,
                "components": [
                    {"type": 1, "components": [{"type": 4, "custom_id": field}]}
                ],
            },
        }

    def submit_modal(
        self, msg, modal_custom_id, fields, guild_id, interaction_token="", modal_id=""
    ):
        self.submitted.append((modal_custom_id, fields, modal_id))
        assert self.pending_modal, "submit tanpa modal!"
        self.pending_modal = False
        amount = int(fields[0][1])
        if self.pending_itembuy is not None:
            slug = self.pending_itembuy
            self.pending_itembuy = None
            self.owned[slug] = self.owned.get(slug, 0) + amount
            self.reply(f"Pembelian {amount} {NAMES[slug]} berhasil!")
            self.current = "shop"
            self._show()
            return None
        self.gems -= amount * cfg.WL_PRICE
        self.current = "locks"
        self._show()
        self.reply(f"Pembelian {amount} WL berhasil!\nGems: {self.fmt_gems()}")
        return None


def main():
    gw = FakeGateway()
    api = FakeApi()
    api.gateway = gw
    engine = Engine(api, gw, "200", "1")

    print("== TEST 1: goto locks dari home ==")
    screen, msg = engine.goto("locks")
    assert screen.id == "locks", screen.id
    gems = engine.read_gems(msg)
    assert gems == 250_000, gems
    print("OK: sampai locks, gems terbaca", engine.fmt_int(gems))

    print("== TEST 2: buy_wl (100 + 24 WL, gems sisa 2.000) ==")
    buy_wl.run(engine, {})
    assert api.gems == 2_000, api.gems
    submitted_amounts = [s[1][0][1] for s in api.submitted]
    assert submitted_amounts == [100, 24], submitted_amounts
    print("OK: pembelian 100 + 24 WL, gems akhir", engine.fmt_int(api.gems))

    print("== TEST 3: buy_wl saat gems habis ==")
    buy_wl.run(engine, {})
    print("OK: berhenti karena gems < floor")

    print("== TEST 4: autofarm on (regex nilai bold 'Auto Farm: **OFF**') ==")
    api.autofarm = "OFF"
    autofarm.run(engine, {"mode": "on"})
    assert api.autofarm == "ON"
    print("OK: auto farm ON")

    print("== TEST 5: autofarm sudah ON, idempotent ==")
    autofarm.run(engine, {"mode": "on"})
    assert api.autofarm == "ON"
    print("OK: idempotent")

    print("== TEST 6: watch 1 siklus (clover dipakai; arroz & benedict dibeli 5 lalu dipakai) ==")
    api.gems = 250_000
    api.owned = {"clover": 2, "arroz": 0, "eggs_benedict": 0}
    run_watch(engine, {"iterations": 1, "minutes": 0.001})
    assert api.owned == {"clover": 1, "arroz": 4, "eggs_benedict": 4}, api.owned
    itembuys = [s for s in api.submitted if "itembuy" in s[0]]
    assert [int(f[1][0][1]) for f in itembuys][-2:] == [5, 5], api.submitted
    assert api.autofarm == "ON"
    assert set(api.active) == set(NAMES.values())
    print("OK:", api.owned)

    print("== TEST 7: buffs saat semua masih aktif -> stok tidak terbuang ==")
    buffs.run(engine, {})
    assert api.owned == {"clover": 1, "arroz": 4, "eggs_benedict": 4}, api.owned
    assert len([s for s in api.submitted if "itembuy" in s[0]]) == 2
    print("OK: tidak ada konsumsi ulang selama buff aktif")

    print("== TEST 8: buff kedaluwarsa -> stok terpakai ==")
    api.active.clear()
    buffs.run(engine, {})
    assert api.owned == {"clover": 0, "arroz": 3, "eggs_benedict": 3}, api.owned
    print("OK:", api.owned)

    print("== TEST 9: clover aktif tidak dibuang; arroz & benedict stok dipakai ==")
    api.active.clear()
    api.active["Lucky Clover"] = 600
    api.owned["clover"] = 5
    buffs.run(engine, {})
    assert api.owned == {"clover": 5, "arroz": 2, "eggs_benedict": 2}, api.owned
    parsed = engine.read_active_buffs()
    assert parsed.get("Lucky Clover") == 600, parsed
    print("OK: clover tersisa 5", api.owned, "parser buff:", parsed)

    print("== TEST 10: regex warning 'timer was not refreshed' ==")
    assert RX_ALREADY.search(
        "?? Warning: Item consumed, but the active timer was not refreshed."
    )
    assert RX_ALREADY.search("Item ini sudah aktif di slot buff kamu.")
    print("OK: pesan ⚠️ terdeteksi sebagai 'sudah aktif', bukan gagal")

    print("== TEST 11: read_farmable_stock terbaca dari home ==")
    engine.goto("home")
    stock = engine.read_farmable_stock()
    assert stock == 17_447, stock
    print("OK: stock terbaca", stock)

    print("== TEST 12: read_farmable_stock saat 0 ==")
    api.farmable_stock = 0
    engine.goto("home")
    stock = engine.read_farmable_stock()
    assert stock == 0, stock
    print("OK: stock 0 terbaca", stock)

    print("== TEST 13: buy_farmable (pot o' gems -> buy max -> back to home) ==")
    engine.buy_farmable("pot o' gems")
    assert engine.screen.id == "home", engine.screen.id
    assert api.farmable_stock == 20_000, api.farmable_stock
    assert engine.read_farmable_stock() == 20_000
    print("OK: buy_farmable sukses, stock sekarang", api.farmable_stock)

    print("== TEST 14: anti-AFK prompt ('are you still there?' -> 'Yes, keep farming') ==")
    afk_msg = make_msg(
        999,
        "@User, are you still there?",
        [("gc:keep_farm", "Yes, keep farming")],
    )
    assert engine.is_anti_afk_prompt(afk_msg) is True
    clicked = []
    orig_click = engine.api.click_button
    engine.api.click_button = lambda m, cid, gid: clicked.append(cid)
    res = engine.handle_anti_afk(afk_msg)
    assert res is True
    assert clicked == ["gc:keep_farm"], clicked
    engine.api.click_button = orig_click
    print("OK: anti-AFK terdeteksi dan direspons otomatis")

    print("== TEST 15: autofarm mode prep (stock 0 dibeli, buff dipakai, autofarm ON) ==")
    api.farmable_stock = 0
    api.autofarm = "OFF"
    api.active.clear()
    api.owned["clover"] = 1
    autofarm.run(engine, {"mode": "prep"})
    assert api.farmable_stock == 20_000, api.farmable_stock
    assert api.autofarm == "ON", api.autofarm
    assert "Lucky Clover" in api.active, api.active
    print("== TEST 16: clover bypass saat clover_checked=True ==")
    api.active.clear()
    api.active["Arroz Con Pollo"] = 1800
    api.active["Eggs Benedict"] = 1800
    api.owned["clover"] = 0
    visited = []
    orig_goto = engine.goto

    def track_goto(scr):
        visited.append(scr)
        return orig_goto(scr)

    engine.goto = track_goto
    buffs.run(engine, {})
    engine.goto = orig_goto
    assert "Lucky Clover" not in api.active
    assert "consumables" not in visited, f"Consumables was visited despite clover bypass: {visited}"
    print("OK: clover di-bypass saat clover_checked aktif")

    print("== TEST 17: _press_kembali mencocokkan '← Item' ==")
    engine.goto("consumables")
    lost_doc = api.render_consumables(api.PANEL_ID)
    engine._session_msgs = [lost_doc]
    assert engine._press_kembali() is True

    # Disabled button does not crash with NavError
    disabled_doc = api.render_consumables(api.PANEL_ID)
    for row in disabled_doc.get("components", []):
        for comp in row.get("components", []):
            comp["disabled"] = True
    engine._session_msgs = [disabled_doc]
    assert engine._press_kembali() is False
    print("OK: fallback _press_kembali sukses menekan '← Item' dan tahan disabled button")

    print("\nSEMUA TEST LULUS")


if __name__ == "__main__":
    main()
