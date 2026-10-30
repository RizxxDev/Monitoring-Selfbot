import logging
import random
import re
import sys
import time

import config as cfg
from core.api import ApiError, GemsExhaustedError
from core.gateway import mask as mask_id
from core.screens import SCREENS, SOURCES, route_steps

log = logging.getLogger("growcord.bot")


def set_console_title(title_text):
    clean = str(title_text).replace("\n", " ").strip()
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(clean)
        except Exception:
            pass
    try:
        sys.stdout.write(f"\033]0;{clean}\007")
        sys.stdout.flush()
    except Exception:
        pass


class NavError(Exception):
    pass


class Engine:
    def __init__(self, api, gateway, channel_id, guild_id=""):
        self.api = api
        self.gw = gateway
        self.channel_id = str(channel_id)
        self.guild_id = guild_id
        self.msg = None       # pesan layar terkini yang terdeteksi
        self.screen = None
        self._session_msgs = []
        self.last_click_id = ""
        self.afk_counter = 0
        self.last_known_stock = "?"
        self.last_known_buffs = 0
        self.last_known_state = "ON"
        # Dynamic session synchronization
        if hasattr(self.gw, "channel_id"):
            self.gw.channel_id = str(self.channel_id)
        if hasattr(self.api, "_session_provider"):
            self.api._session_provider = lambda: self.gw.session_id if self.gw else ""
        if hasattr(self.gw, "on_session"):
            self.gw.on_session = lambda sid: setattr(self.api, "session_id", sid)
        self._rx_gem = re.compile(
            r"Gems\*{0,2}\s*[:=]\s+\*{0,2}([\d.,]+)\*{0,2}", re.IGNORECASE
        )
        self._rx_autofarm = re.compile(
            r"Auto\s*Farm\s*:\s*[^a-zA-Z\n]*(ON|OFF)\b", re.IGNORECASE
        )

    # ------------------------------------------------------------------
    # utilitas
    # ------------------------------------------------------------------
    def sleep_min_max(self, minmax, extra=0.0):
        lo, hi = minmax
        time.sleep(random.uniform(lo, hi) + extra)

    @staticmethod
    def fmt_int(value):
        return f"{int(value):,}".replace(",", ".")

    @staticmethod
    def fmt_durasi(secs):
        secs = int(secs or 0)
        if secs >= 86400:
            return f"{secs // 86400}d {(secs % 86400) // 3600}h {(secs % 3600) // 60}m"
        if secs >= 3600:
            return f"{secs // 3600}h {(secs % 3600) // 60}m {(secs % 60)}s"
        if secs >= 60:
            return f"{secs // 60}m {secs % 60}s"
        return f"{secs}s"

    @staticmethod
    def _collect_cv2_text(node, parts):
        if isinstance(node, dict):
            if node.get("type") == 10 and node.get("content"):
                parts.append(str(node["content"]))
            for value in node.values():
                if isinstance(value, (dict, list)):
                    Engine._collect_cv2_text(value, parts)
        elif isinstance(node, list):
            for item in node:
                Engine._collect_cv2_text(item, parts)

    @staticmethod
    def message_text(msg):
        parts = [msg.get("content") or ""]
        for embed in msg.get("embeds") or []:
            author = embed.get("author") or {}
            footer = embed.get("footer") or {}
            parts.extend(
                [
                    author.get("name") or "",
                    embed.get("title") or "",
                    embed.get("description") or "",
                    footer.get("text") or "",
                ]
            )
        Engine._collect_cv2_text(msg.get("components") or [], parts)
        return "\n".join(p for p in parts if p)

    @staticmethod
    def message_buttons(msg):
        result = []

        def walk(node):
            if isinstance(node, dict):
                ntype = node.get("type")
                if ntype in (2, 3):
                    label = node.get("label") or node.get("placeholder") or ""
                    result.append(
                        {
                            "type": ntype,
                            "custom_id": node.get("custom_id") or "",
                            "label": str(label).strip(),
                            "disabled": bool(node.get("disabled")),
                        }
                    )
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(msg.get("components") or [])
        return result

    @staticmethod
    def _is_growcord(msg, app_id):
        author = msg.get("author") or {}
        if app_id and str(author.get("id")) == str(app_id):
            return True
        if author.get("bot"):
            return True
        return author.get("username", "").lower() == "growcord"

    def abort_reason(self, text):
        low = (text or "").lower()
        for pattern in cfg.ABORT_PATTERNS:
            if pattern.lower() in low:
                return pattern
        return None

    # ------------------------------------------------------------------
    # deteksi layar & navigasi
    # ------------------------------------------------------------------
    def fetch_messages(self, limit=30):
        return self.api.get_messages(self.channel_id, limit=limit)

    def locate(self, msgs=None):
        docs = msgs if msgs is not None else self.fetch_messages()
        self._session_msgs = docs
        for msg in docs:
            if not self._is_growcord(msg, cfg.GROWCORD_APP_ID):
                continue
            text = self.message_text(msg)
            for screen in SCREENS:
                if screen.matches(text):
                    self.screen, self.msg = screen, msg
                    return screen, msg
        self.screen, self.msg = None, None
        return None, None

    def _match_button(self, msg, pattern):
        candidates = [c for c in self.message_buttons(msg) if pattern.search(c["label"])]
        if not candidates:
            return None
        for comp in candidates:
            if not comp["disabled"]:
                return comp
        raise NavError(
            f'Tombol "{candidates[0]["label"]}" ada tapi disabled '
            f"(mungkin sedang cooldown / tidak tersedia)."
        )

    def _click(self, msg, button, action_desc):
        log.info("[klik] %s", action_desc)
        if not button.get("custom_id"):
            raise NavError(
                f'Tombol "{button["label"]}" tidak memiliki custom_id '
                f"(kemungkinan disabled)."
            )
        try:
            return self.api.click_button(msg, button["custom_id"], self.guild_id)
        except ApiError:
            self.locate()  # refresh pesan agar info error tidak basi
            raise

    def click_screen_button(self, screen_id, logical, msg=None):
        screen = SOURCES.get(screen_id)
        if screen is None:
            raise NavError(f"Layar '{screen_id}' tidak terdaftar")
        doc = msg if msg is not None else self.msg
        if doc is None or (self.screen and self.screen.id != screen_id):
            _, doc = self.locate()
        if doc is None:
            raise NavError(f"Pesan layar '{screen_id}' tidak ditemukan")
        spec = screen.buttons.get(logical)
        if spec is None:
            raise NavError(f"Tombol '{logical}' tidak ada di layar '{screen_id}'")
        button = self._match_button(doc, screen.pattern(logical))
        if button is None:
            found = ", ".join(b["label"] for b in self.message_buttons(doc)) or "-"
            raise NavError(
                f'Tombol "{spec}" tidak ditemukan di layar {screen_id}. '
                f"Tombol terlihat: {found}"
            )
        self.last_click_id = button["custom_id"]
        return self._click(doc, button, f"[{screen_id}] {button['label']}")

    @staticmethod
    def _guess_modal(button_custom_id):
        parts = str(button_custom_id).split(":")
        # gc:<uid>:<aksi>:<arg> -> gc:<uid>:<aksi>modal:<arg>
        if len(parts) >= 4 and parts[2] and "modal" not in parts[2]:
            parts[2] += "modal"
            guess = ":".join(parts)
            log.warning(
                "[modal] tidak terdeteksi realtime, pakai tebakan custom_id=%s "
                "field=amount (tebakan bot Growcord)",
                mask_id(guess),
            )
            return {"custom_id": guess, "id": "", "field_id": "amount", "max_length": None, "token": ""}
        return None

    @staticmethod
    def _select_options(doc, custom_id):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == 3 and str(node.get("custom_id")) == str(custom_id):
                    found.extend(node.get("options") or [])
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(doc.get("components") or [])
        return found

    def click_screen_select(self, screen_id, logical, option_pat, msg=None):
        """Pilih opsi pada select menu di layar tertentu (pola label opsi)."""
        screen = SOURCES.get(screen_id)
        if screen is None:
            raise NavError(f"Layar '{screen_id}' tidak terdaftar")
        doc = msg if msg is not None else self.msg
        if doc is None or (self.screen and self.screen.id != screen_id):
            _, doc = self.locate()
        if doc is None:
            raise NavError(f"Pesan layar '{screen_id}' tidak ditemukan")
        spec = screen.buttons.get(logical)
        if spec is None:
            raise NavError(f"Select '{logical}' tidak ada di layar '{screen_id}'")
        sel = self._match_button(doc, screen.pattern(logical))
        if sel is None:
            found = ", ".join(b["label"] for b in self.message_buttons(doc)) or "-"
            raise NavError(
                f'Select "{spec}" tidak ditemukan di layar {screen_id}. Komponen: {found}'
            )
        options = self._select_options(doc, sel["custom_id"])
        if options:
            pick = next(
                (
                    o for o in options
                    if option_pat.search(o.get("label") or "")
                    or option_pat.search(o.get("value") or "")
                    or option_pat.search(o.get("description") or "")
                ),
                None,
            )
        else:
            pick = None
        if pick is None:
            listed = ", ".join(o.get("label", "?") for o in options) or "(kosong)"
            raise NavError(
                f"Opsi '{option_pat.pattern}' tidak ketemu pada select di {screen_id}. "
                f"Opsi tersedia: {listed}"
            )
        log.info("[select] %s -> %s", spec, pick.get("label"))
        self.last_click_id = sel["custom_id"]
        return self.api.click_select(
            doc, sel["custom_id"], [pick.get("value")], self.guild_id
        )

    def wait_selected(self, nama_item, timeout=6.0):
        """Tunggu teks 'Dipilih: nama' muncul setelah memilih opsi select."""
        pat = re.compile(
            rf"(?:Dipilih|Selected)\s*:?.*?{re.escape(nama_item)}",
            re.IGNORECASE,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.fetch_messages(30)
            for doc in docs:
                if not self._is_growcord(doc, cfg.GROWCORD_APP_ID):
                    continue
                text = self.message_text(doc)
                if pat.search(text):
                    self.screen, self.msg = self.locate(docs)
                    return True
            time.sleep(0.8)
        return False

    def _submit_spawned(self, modal, value):
        log.info("[form] isi %s=%s lalu submit", modal["field_id"], value)
        doc = self.msg or self.locate()[1]
        if doc is None:
            raise NavError("pesan untuk submit modal tidak ketemu")
        return self.api.submit_modal(
            doc,
            modal["custom_id"],
            [(modal["field_id"], value)],
            self.guild_id,
            interaction_token=modal.get("token") or "",
            modal_id=modal.get("id") or "",
        )

    def _press_kembali(self):
        for doc in self._session_msgs:
            if not self._is_growcord(doc, cfg.GROWCORD_APP_ID):
                continue
            if not doc.get("components"):
                continue
            try:
                button = self._match_button(
                    doc,
                    re.compile(r"Kembali|\bBack\b|←\s*(?:Items?|Kembali|Back)\b", re.IGNORECASE),
                )
            except NavError:
                continue
            if button:
                self._click(
                    doc, button, f"(tersesat) Kembali dari pesan {doc['id'][-6:]}"
                )
                return True
        return False

    def goto(self, screen_id):
        target = SOURCES.get(screen_id)
        if target is None:
            raise NavError(f"Layar tujuan '{screen_id}' tidak terdaftar di screens.py")
        for _ in range(cfg.NAV_MAX_STEPS):
            screen, msg = self.locate()
            if screen is not None and screen.id == screen_id:
                return screen, msg
            if screen is None:
                log.info("layar tidak dikenali, mencoba tombol Kembali...")
                if not self._press_kembali():
                    log.info("tombol Kembali tidak ditemukan, menunggu 3s")
                    time.sleep(3.0)
            else:
                steps = route_steps(screen.id, screen_id)
                if steps:
                    try:
                        self.click_screen_button(screen.id, steps[0])
                    except NavError as exc:
                        log.warning("[nav] %s; fallback tombol Kembali", exc)
                        if not self._press_kembali():
                            time.sleep(3.0)
                else:
                    log.info(
                        "route %s -> %s tidak ketemu, coba Kembali", screen.id, screen_id
                    )
                    if not self._press_kembali():
                        time.sleep(3.0)
            self.sleep_min_max(cfg.DELAY_NAV)
        screen, msg = self.locate()
        if screen is not None and screen.id == screen_id:
            return screen, msg
        where = screen.id if screen else "tidak dikenal"
        raise NavError(
            f"gagal sampai layar '{screen_id}' setelah {cfg.NAV_MAX_STEPS} langkah "
            f"(posisi terakhir: {where})"
        )

    # ------------------------------------------------------------------
    # membaca data dari layar
    # ------------------------------------------------------------------
    def read_gems(self, msg=None):
        doc = msg or self.msg
        if doc is None:
            return None
        wx = self._rx_gem.search(self.message_text(doc))
        if wx:
            digits = re.sub(r"\D", "", wx.group(1))
            # jam emoji "Gems:<snowflake>" tidak punya spasi; regex wajib
            # spasi setelah titik dua sehingga tidak akan tersangkut.
            try:
                return int(digits)
            except ValueError:
                return None
        return None

    def read_active_buffs(self, msgs=None):
        """Kembalikan dict {nama_buff: sisa_detik} dari bagian 'Buff Aktif'."""
        if msgs is not None:
            docs = [msgs] if isinstance(msgs, dict) else msgs
        else:
            docs = self.fetch_messages(30)
        for doc in docs:
            if not self._is_growcord(doc, cfg.GROWCORD_APP_ID):
                continue
            text = self.message_text(doc)
            if "Buff Aktif" not in text and "Aktif Buff" not in text:
                continue
            out = {}
            grab = False
            for line in text.split("\n"):
                head = line.strip()
                if not grab:
                    grab = bool(re.match(r"[*# ]*(Buff\s*Aktif|Aktif\s*Buff)", head, re.I))
                    continue
                if not head.startswith("-"):
                    break
                body = head.lstrip("-").strip()
                rz = re.search(
                    r"^(.*?)(?:\s*\u2022|\s+\|\s+|\s+for)\s*(.+)$", body
                )
                name = rz.group(1).strip() if rz else body
                name = re.sub(r"\*+", "", name).strip()
                dur = rz.group(2) if rz else ""
                seconds = 0
                for angka, satuan in re.findall(r"(\d+)\s*([dhms])", dur, re.I):
                    mult = {"d": 86400, "h": 3600, "m": 60, "s": 1}[satuan.lower()]
                    seconds += int(angka) * mult
                if name:
                    out[name] = seconds
            return out
        return {}

    def read_autofarm_state(self, msgs=None):
        if msgs is not None:
            docs = [msgs] if isinstance(msgs, dict) else msgs
        else:
            docs = self.fetch_messages(30)
        for doc in docs:
            if not self._is_growcord(doc, cfg.GROWCORD_APP_ID):
                continue
            rx = self._rx_autofarm.search(self.message_text(doc))
            if rx:
                state = rx.group(1).upper()
                if state.startswith("ON"):
                    return "ON"
                if state.startswith("OFF"):
                    return "OFF"
                return state
        return None

    def read_farmable_stock(self, msgs=None):
        """Kembalikan jumlah block farmable yang tersisa (int) atau None jika tidak ditemukan."""
        if msgs is not None:
            docs = [msgs] if isinstance(msgs, dict) else msgs
        else:
            docs = [self.msg] if self.msg else self.fetch_messages(30)
        for doc in docs:
            if not self._is_growcord(doc, cfg.GROWCORD_APP_ID):
                continue
            text = self.message_text(doc)
            # 1. Baca dari "Inventori: 17.447 / 20.000" atau "Inventory: 17,447 / 20,000"
            m_inv = re.search(r"Inventor(?:i|y)\s*:\s*\*{0,2}([\d.,]+)\s*/", text, re.I)
            if m_inv:
                digits = re.sub(r"\D", "", m_inv.group(1))
                if digits:
                    return int(digits)

            # 2. Baca dari "Farmable Saat Ini: ... (17.447 Block)" atau "Current Farmable: ... (17,447 Block)"
            m_block = re.search(
                r"(?:Farmable\s*Saat\s*Ini|Current\s*Farmable|Farmable)\s*:.*?\((\d[\d.,]*)\s*Blocks?\)",
                text,
                re.I,
            )
            if m_block:
                digits = re.sub(r"\D", "", m_block.group(1))
                if digits:
                    return int(digits)

            # 3. Cek indikasi kosong / habis
            if re.search(
                r"(?:Farmable\s*Saat\s*Ini|Current\s*Farmable|Farmable)\s*:\s*(?:Tidak\s*ada|None|-|Kosong|Empty)",
                text,
                re.I,
            ):
                return 0
            if re.search(r"Inventor(?:i|y)\s*:\s*\*{0,2}0\b", text, re.I):
                return 0
        return None

    def buy_farmable(self, item_name="pot o' gems"):
        """Beli farmable di Toko -> Farmable -> Select Item -> Buy Max -> Home."""
        log.info("[farmable] Menuju toko farmable untuk membeli '%s'...", item_name)
        screen, msg = self.goto("shop_farmable")
        doc = msg or self.msg or self.locate()[1]
        if doc is None:
            raise NavError("Layar shop_farmable tidak ditemukan")

        # 1. Pilih item di select menu
        clean_name = item_name.replace("'", "").replace("’", "")
        rx_item = re.compile(
            rf"{re.escape(item_name)}|{re.escape(clean_name)}|pot\s*o'?\s*gems",
            re.I,
        )
        try:
            self.click_screen_select("shop_farmable", "select_item", rx_item, msg=doc)
        except NavError as exc:
            log.warning("[farmable] click_screen_select spesifik gagal (%s), mencari select component...", exc)
            sel = next((c for c in self.message_buttons(doc) if c.get("type") == 3), None)
            if sel:
                options = self._select_options(doc, sel["custom_id"])
                pick = next(
                    (
                        o for o in options
                        if rx_item.search(o.get("label", ""))
                        or rx_item.search(o.get("value", ""))
                    ),
                    None,
                )
                if pick:
                    log.info("[farmable] Memilih opsi: %s (%s)", pick.get("label"), pick.get("value"))
                    self.api.click_select(doc, sel["custom_id"], [pick["value"]], self.guild_id)
                else:
                    raise NavError(f"Opsi '{item_name}' tidak ditemukan di select menu shop_farmable")
            else:
                raise

        time.sleep(1.0)
        reply = self.wait_bot_reply(cfg.REPLY_TIMEOUT)
        target_msg = reply if reply is not None else (self.msg or self.locate()[1])

        # 2. Cari tombol Buy Max / Beli Max
        pat_max = re.compile(r"\b(?:buy|beli)\s*max\b|\bmax\b", re.I)
        btn_max = None
        if target_msg:
            for b in self.message_buttons(target_msg):
                if pat_max.search(b["label"]) and not b.get("disabled"):
                    btn_max = b
                    break

        if btn_max is None:
            _, fresh = self.locate()
            if fresh:
                target_msg = fresh
                for b in self.message_buttons(target_msg):
                    if pat_max.search(b["label"]) and not b.get("disabled"):
                        btn_max = b
                        break

        if btn_max is None:
            raise NavError("Tombol 'Buy Max' tidak ditemukan di layar shop_farmable")

        log.info("[farmable] Menekan tombol [%s]...", btn_max["label"])
        self.api.click_button(target_msg, btn_max["custom_id"], self.guild_id)

        modal = self.capture_modal(1.5)
        if modal:
            log.info("[farmable] Form modal muncul, submit dengan nilai 'max'...")
            self._submit_spawned(modal, "max")

        reply_buy = self.wait_bot_reply(cfg.REPLY_TIMEOUT)
        if reply_buy:
            text = self.message_text(reply_buy)
            reason = self.abort_reason(text)
            if reason:
                low = reason.lower()
                if any(w in low for w in ("tidak cukup", "insufficient", "kehabisan", "gems")):
                    raise GemsExhaustedError(f"Pembelian farmable ditolak (Gems habis): {reason}")
                raise NavError(f"Pembelian farmable ditolak: {reason}")
            log.info("[farmable] Hasil pembelian: %s", text.replace("\n", " ")[:140])

        # 3. Kembali ke main menu (home)
        log.info("[farmable] Kembali ke main menu (home)...")
        self.goto("home")

    def update_status_title(self, stock=None, buffs=None, state="ON"):
        """Perbarui judul jendela konsol/CMD untuk pemantauan realtime."""
        if stock is None:
            stock = getattr(self, "last_known_stock", "?")
        else:
            self.last_known_stock = stock
        if buffs is None:
            buffs = getattr(self, "last_known_buffs", 0)
        else:
            self.last_known_buffs = (
                len(buffs) if isinstance(buffs, dict)
                else (buffs if isinstance(buffs, int) else 0)
            )
        state_str = str(state or getattr(self, "last_known_state", "ON")).upper()
        self.last_known_state = state_str

        stock_str = (
            f"{int(stock):,}".replace(",", ".")
            if isinstance(stock, (int, float))
            else str(stock)
        )
        buff_count = self.last_known_buffs
        afk_count = getattr(self, "afk_counter", 0)
        title = (
            f"Growcord Bot [{state_str}] | Stock: {stock_str} | "
            f"Buffs: {buff_count}/3 | AFK Handled: {afk_count}"
        )
        set_console_title(title)

    def safe_drain_events(self):
        """Kuras antrean event Gateway tanpa menghilangkan prompt Anti-AFK.
        Jika ada event 'are you still there?' yang tiba saat navigasi,
        segera tangani (klik 'Yes, keep farming') sebelum membuang event lama lainnya.
        """
        handled = 0
        while True:
            event = self.gw.pop_event(timeout=0)
            if event is None:
                break
            kind, data, _ts = event
            if kind in ("message_new", "message_edit") and isinstance(data, dict):
                if self.is_anti_afk_prompt(data):
                    log.info("[safe-drain] ⚠️ Prompt Anti-AFK ditemukan di antrean! Merespons...")
                    if self.handle_anti_afk(data):
                        handled += 1
        return handled

    def is_anti_afk_prompt(self, msg):
        """Cek apakah pesan merupakan tantangan 'are you still there?' dari Growcord."""
        if not msg or not isinstance(msg, dict):
            return False
        msg_chan = str(msg.get("channel_id") or "")
        if self.channel_id and msg_chan and msg_chan != str(self.channel_id):
            return False
        if not self._is_growcord(msg, cfg.GROWCORD_APP_ID):
            return False
        text = self.message_text(msg)
        if re.search(r"are\s*you\s*still\s*there\??", text, re.I):
            return True
        for b in self.message_buttons(msg):
            if re.search(r"yes[,\s]+keep\s+farming", b.get("label", ""), re.I):
                return True
        return False

    def handle_anti_afk(self, msg):
        """Merespons prompt 'are you still there?' dengan mengklik 'Yes, keep farming'."""
        buttons = self.message_buttons(msg)
        pat = re.compile(r"yes[,\s]+keep\s+farming", re.I)
        target = next(
            (b for b in buttons if pat.search(b.get("label", "")) and not b.get("disabled")),
            None,
        )
        if target and target.get("custom_id"):
            log.info(
                "[anti-afk] ⚠️ Terdeteksi prompt 'are you still there?' -> Mengklik [%s]...",
                target["label"],
            )
            delay_range = getattr(cfg, "DELAY_ANTI_AFK", (1.2, 2.2))
            time.sleep(random.uniform(*delay_range))
            try:
                self.api.click_button(msg, target["custom_id"], self.guild_id)
                self.afk_counter = getattr(self, "afk_counter", 0) + 1
                self.update_status_title()
                log.info(
                    "[anti-afk] ✅ Berhasil klik [%s]! (Total ditangani: %d)",
                    target["label"],
                    self.afk_counter,
                )
                return True
            except Exception as exc:
                log.error("[anti-afk] Gagal mengklik tombol [%s]: %s", target["label"], exc)
                return False
        return False

    def check_recent_anti_afk(self, limit=10):
        """Periksa pesan-pesan terbaru untuk memastikan tidak ada prompt anti-AFK tertunda."""
        docs = self.fetch_messages(limit)
        for doc in docs:
            if self.is_anti_afk_prompt(doc):
                return self.handle_anti_afk(doc)
        return False

    def wait_idle(self, duration, on_event=None):
        """Menunggu selama duration detik secara responsif terhadap event realtime (anti-AFK)."""
        deadline = time.time() + duration
        while time.time() < deadline:
            remaining = deadline - time.time()
            event = self.gw.pop_event(timeout=min(1.0, max(0.1, remaining)))
            if event is None:
                continue
            kind, data, _ts = event
            if kind in ("message_new", "message_edit"):
                msg_chan = str(data.get("channel_id") or "")
                if self.channel_id and msg_chan and msg_chan != str(self.channel_id):
                    continue
                if self.is_anti_afk_prompt(data):
                    self.handle_anti_afk(data)
                    continue
            if on_event:
                res = on_event(kind, data)
                if res is not None and res is False:
                    break

    # ------------------------------------------------------------------
    # realtime (gateway)
    # ------------------------------------------------------------------
    def capture_modal(self, timeout, msg_id=None):
        deadline = time.time() + timeout
        stashed = []
        try:
            while time.time() < deadline:
                remaining = deadline - time.time()
                event = self.gw.pop_event(timeout=min(0.5, max(0.05, remaining)))
                if event is None:
                    continue
                kind, data, _ts = event
                if kind != "interaction":
                    stashed.append(event)
                    continue
                if str(data.get("channel_id")) != self.channel_id:
                    continue
                if msg_id and str(data.get("message", {}).get("id")) != str(msg_id):
                    continue
                modal = self._modal_from_interaction(data)
                if modal:
                    log.info(
                        "[modal] terdeteksi form (custom_id=%s, field=%s)",
                        mask_id(modal["custom_id"]),
                        mask_id(modal["field_id"]),
                    )
                    return modal
            return None
        finally:
            for item in stashed:
                self.gw.events.put(item)

    @staticmethod
    def _modal_fields(components):
        out = []
        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == 4 and node.get("custom_id"):
                    out.append(
                        {
                            "custom_id": node["custom_id"],
                            "max_length": node.get("max_length"),
                            "required": node.get("required", True),
                        }
                    )
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(components)
        return out

    @staticmethod
    def _modal_from_interaction(data):
        body = data.get("data") or data
        fields = Engine._modal_fields(body.get("components") or [])
        if not fields:
            return None
        return {
            "custom_id": body.get("custom_id") or "",
            "id": data.get("id") or body.get("id") or "",
            "field_id": fields[0]["custom_id"],
            "max_length": fields[0].get("max_length"),
            "token": data.get("token") or "",
        }

    def wait_bot_reply(self, timeout, msg_id=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            event = self.gw.pop_event(timeout=min(0.5, max(0.05, remaining)))
            if event is None:
                continue
            kind, data, _ts = event
            if kind not in ("message_new", "message_edit"):
                continue
            if str(data.get("channel_id")) != self.channel_id:
                continue
            if not self._is_growcord(data, cfg.GROWCORD_APP_ID):
                continue
            if msg_id and str(data.get("id")) != str(msg_id):
                continue
            # abaikan gema dari aksi sendiri (user self)
            inter = data.get("interaction") or {}
            user_id = (inter.get("user") or {}).get("id")
            if user_id and str(user_id) == str(self.gw.user_id):
                continue
            return data
        return None

    # ------------------------------------------------------------------
    # alur beli berbantu form
    # ------------------------------------------------------------------
    def buy_with_form(self, screen_id, button_logical, amount, source_msg=None):
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            raise NavError(f"Jumlah tidak valid: {amount}")
        if amount < 1:
            raise NavError("Jumlah minimal 1")
        source_msg = source_msg or self.msg
        if source_msg is None:
            source_msg = self.locate()[1]
        if source_msg is None:
            raise NavError("pesan sumber tombol tidak ketemu")
        limit_amount = amount
        self.click_screen_button(screen_id, button_logical)
        modal = self.capture_modal(cfg.MODAL_TIMEOUT)
        if modal is None:
            modal = self._guess_modal(self.last_click_id)
        if modal is not None:
            if cfg.MODAL_CUSTOM_ID:
                modal["custom_id"] = cfg.MODAL_CUSTOM_ID
                log.info(
                    "[modal] pakai custom_id override (%s)",
                    mask_id(modal["custom_id"]),
                )
            if cfg.MODAL_FIELD_CUSTOM_ID:
                modal["field_id"] = cfg.MODAL_FIELD_CUSTOM_ID
                log.info(
                    "[modal] pakai field_id override (%s)",
                    mask_id(modal["field_id"]),
                )
            if modal.get("max_length"):
                try:
                    max_len = int(modal["max_length"])
                    if max_len > 0 and len(str(amount)) > max_len:
                        limit_amount = int("9" * max_len)
                        log.warning(
                            "[modal] panjang digit %s melebihi max_length (%s), disesuaikan ke %s",
                            amount,
                            max_len,
                            limit_amount,
                        )
                except (ValueError, TypeError):
                    pass
            token = modal["token"]
            modal_c_id = modal["custom_id"]
            field_id = modal["field_id"]
            modal_int_id = modal.get("id") or ""
        else:
            if not cfg.MODAL_CUSTOM_ID or not cfg.MODAL_FIELD_CUSTOM_ID:
                log.error(
                    "[modal] tidak terdeteksi lewat gateway dan config belum diisi.\n"
                    "  Jalankan: python main.py inspect --click %s\n"
                    "  lalu salin nilai cetakan ke MODAL_CUSTOM_ID / MODAL_FIELD_CUSTOM_ID "
                    "di config.py",
                    button_logical,
                )
                raise NavError("modal tidak terdeteksi")
            log.warning("[modal] fallback ke config.py")
            modal_c_id = cfg.MODAL_CUSTOM_ID
            field_id = cfg.MODAL_FIELD_CUSTOM_ID
            token = ""
            modal_int_id = ""

        log.info("[form] isi jumlah=%s lalu submit", limit_amount)
        self.api.submit_modal(
            self.msg or source_msg,
            modal_c_id,
            [(field_id, limit_amount)],
            self.guild_id,
            interaction_token=token,
            modal_id=modal_int_id,
        )
        return limit_amount
