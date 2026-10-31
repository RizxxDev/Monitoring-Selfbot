"""
=============================================================================
             GROWCORD AUTOFARM & ANTI-AFK - ALL-IN-ONE SCRIPT
=============================================================================
Skrip tunggal terpadu (single script) untuk Growcord Farm Discord:
1. Cek stock farmable di main menu:
   - Jika habis (<= 0), beli di Toko -> Farmable -> Pot o' Gems -> Buy Max -> Home.
2. Cek status efek buff (Lucky Clover, Arroz Con Pollo, Eggs Benedict):
   - Jika belum aktif, gunakan dari inventory (Item -> Consumables).
   - Jika tidak ada di inventory, beli Arroz & Eggs Benedict di Toko Consumables.
   - (Catatan: Lucky Clover tidak dijual di toko, di-skip jika tidak punya).
3. Nyalakan Auto Farm:
   - Jika Auto Farm di main menu masih OFF, klik Farm sehingga berubah jadi ON.
4. Standby & Idle Listener:
   - Memantau event Discord Gateway secara realtime.
   - Jika bot mengirim tantangan Anti-AFK 'are you still there?', otomatis
     klik tombol 'Yes, keep farming'.
   - Pemeriksaan berkala otomatis agar buff & stok farmable tidak pernah putus.

Jalankan langsung:
    python autofarm.py
=============================================================================
"""

from collections import deque
import json
import logging
import os
import queue
import random
import re
import sys
import threading
import time

import requests
import websocket

# =============================================================================
#  KONFIGURASI (dapat membaca config.py atau environment variable / default)
# =============================================================================
try:
    import config as _cfg
except ImportError:
    _cfg = None


def get_conf(name, default):
    if _cfg and hasattr(_cfg, name):
        val = getattr(_cfg, name)
        if val is not None and val != "":
            return val
    return os.getenv(name, default)


TOKEN = get_conf("TOKEN", os.getenv("DISCORD_TOKEN", ""))
CHANNEL_ID = str(get_conf("CHANNEL_ID", os.getenv("GROWCORD_CHANNEL", "")))
GROWCORD_APP_ID = get_conf("GROWCORD_APP_ID", "")

# Item farmable yang dibeli saat stock habis
FARMABLE_ITEM = get_conf("FARMABLE_ITEM", "pot o' gems")

# Interval pengecekan berkala (detik) saat sedang standby
CHECK_INTERVAL = int(get_conf("AUTOFARM_CHECK_INTERVAL", 300))

# Delays & Timeouts
DELAY_NAV = getattr(_cfg, "DELAY_NAV", (2.0, 3.5))
DELAY_BUY = getattr(_cfg, "DELAY_BUY", (2.5, 4.0))
MODAL_TIMEOUT = float(getattr(_cfg, "MODAL_TIMEOUT", 8.0))
REPLY_TIMEOUT = float(getattr(_cfg, "REPLY_TIMEOUT", 15.0))
NAV_MAX_STEPS = int(getattr(_cfg, "NAV_MAX_STEPS", 15))

USER_AGENT = getattr(
    _cfg,
    "USER_AGENT",
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
)

LOG_FILE = getattr(_cfg, "LOG_FILE", "runs.log")

ABORT_PATTERNS = getattr(
    _cfg,
    "ABORT_PATTERNS",
    [
        "tidak cukup",
        "insufficient",
        "kehabisan",
        "pembelian gagal",
        "terjadi kesalahan",
    ],
)

BASE_API = "https://discord.com/api/v10"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"

log = logging.getLogger("growcord")


# =============================================================================
#  LOGGING & SETUP
# =============================================================================
def setup_logging():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        from logging.handlers import RotatingFileHandler
        handlers.append(
            RotatingFileHandler(
                LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    for name in ("growcord.api", "growcord.gateway"):
        logging.getLogger(name).setLevel(logging.INFO)


def mask(value):
    val = str(value or "")
    if len(val) <= 12:
        return val
    return val[:6] + "..." + val[-4:]


def nonce():
    return str(
        ((int(time.time() * 1000) - 1420070400000) << 22) + random.randint(0, 4194304)
    )


# =============================================================================
#  DISCORD API HTTP CLIENT
# =============================================================================
class ApiError(Exception):
    pass


class AuthError(ApiError):
    pass


class GemsExhaustedError(Exception):
    """Dilempar saat Gems akun habis saat mencoba transaksi di toko."""
    pass


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


class Api:
    def __init__(self, token, user_agent):
        self.session = requests.Session()
        self._session_id = ""
        self._session_provider = None
        self.session.headers.update(
            {
                "Authorization": token,
                "User-Agent": user_agent,
                "Content-Type": "application/json",
                "Origin": "https://discord.com",
                "Referer": "https://discord.com/",
            }
        )

    @property
    def session_id(self):
        if callable(getattr(self, "_session_provider", None)):
            sid = self._session_provider()
            if sid:
                return sid
        return self._session_id

    @session_id.setter
    def session_id(self, val):
        self._session_id = str(val or "")

    def request(self, method, path, payload=None, retries=3):
        url = BASE_API + path
        data = json.dumps(payload) if payload is not None else None
        last_error = "unknown"
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.request(method, url, data=data, timeout=20)
            except requests.RequestException as exc:
                last_error = f"koneksi gagal: {exc}"
                log.warning("%s (percobaan %d/%d)", last_error, attempt, retries)
                time.sleep(2.0 * attempt)
                continue

            if resp.status_code in (200, 201, 202, 204):
                if resp.content:
                    try:
                        return resp.json()
                    except ValueError:
                        return resp.text
                return None

            if resp.status_code == 429:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                wait = float(body.get("retry_after", 1.0) or 1.0)
                log.warning("429 rate limit, menunggu %.1fs", wait)
                time.sleep(wait + 0.5)
                continue

            if resp.status_code == 401:
                raise AuthError(
                    "Token ditolak (401). Token expired / sudah logout. "
                    "Ambil token baru dan perbarui config.py / env DISCORD_TOKEN."
                )

            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:100]}"
                log.warning(
                    "Server Discord error %s (percobaan %d/%d), tunggu %.1fs...",
                    last_error,
                    attempt,
                    retries,
                    2.0 * attempt,
                )
                time.sleep(2.0 * attempt)
                continue

            raise ApiError(
                f"{method} {path} -> HTTP {resp.status_code}: {(resp.text or '')[:300]}"
            )
        raise ApiError(
            f"{method} {path} gagal setelah {retries} percobaan ({last_error})"
        )

    def channel_info(self, channel_id):
        return self.request("GET", f"/channels/{channel_id}")

    def get_messages(self, channel_id, limit=30):
        data = self.request("GET", f"/channels/{channel_id}/messages?limit={limit}")
        return data or []

    @staticmethod
    def _base_payload(msg, guild_id):
        inter = msg.get("interaction") or {}
        actual_guild = msg.get("guild_id") or guild_id or ""
        return {
            "application_id": inter.get("application_id")
            or msg.get("author", {}).get("id"),
            "guild_id": actual_guild,
            "channel_id": msg.get("channel_id"),
            "session_id": "",
            "nonce": nonce(),
        }

    def _fill_session(self, payload):
        if self.session_id:
            payload["session_id"] = self.session_id
        return payload

    @staticmethod
    def _interaction_token(msg):
        inter = msg.get("interaction") or {}
        return inter.get("token") or ""

    def click_button(self, msg, custom_id, guild_id):
        payload = self._base_payload(msg, guild_id)
        payload.update(
            {
                "type": 3,
                "message_id": msg["id"],
                "message_flags": 0,
                "data": {"custom_id": custom_id, "component_type": 2},
            }
        )
        token = self._interaction_token(msg)
        if token:
            payload["token"] = token
        self._fill_session(payload)
        return self.request("POST", "/interactions", payload)

    def click_select(self, msg, custom_id, values, guild_id):
        payload = self._base_payload(msg, guild_id)
        payload.update(
            {
                "type": 3,
                "message_id": msg["id"],
                "message_flags": 0,
                "data": {
                    "custom_id": custom_id,
                    "component_type": 3,
                    "values": values,
                },
            }
        )
        token = self._interaction_token(msg)
        if token:
            payload["token"] = token
        self._fill_session(payload)
        return self.request("POST", "/interactions", payload)

    def submit_modal(
        self,
        msg,
        modal_custom_id,
        fields,
        guild_id,
        interaction_token="",
        modal_id="",
    ):
        values = [
            {"type": 4, "custom_id": field_id, "value": str(value)}
            for field_id, value in fields
        ]
        payload = self._base_payload(msg, guild_id)
        data = {
            "custom_id": modal_custom_id,
            "components": [{"type": 1, "components": values}],
        }
        if modal_id:
            data["id"] = str(modal_id)
        payload.update(
            {
                "type": 5,
                "message_id": msg["id"],
                "message_flags": 0,
                "data": data,
            }
        )
        token = interaction_token or self._interaction_token(msg)
        if token:
            payload["token"] = token
        self._fill_session(payload)
        return self.request("POST", "/interactions", payload)


# =============================================================================
#  DISCORD GATEWAY WEBSOCKET CLIENT
# =============================================================================
class _AuthInvalid(Exception):
    pass


class Gateway:
    def __init__(self, token):
        self.token = token
        self.channel_id = ""
        self.events = queue.Queue(maxsize=300)
        self.seq = None
        self.session_id = ""
        self.user_name = ""
        self.user_id = ""
        self.ready_data = {}
        self.fatal = False
        self.ready = threading.Event()
        self.on_session = None
        self._run = True
        self._stop_hb = None
        self._ws = None
        self.can_resume = True
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.ready.clear()
        self._thread.start()

    def stop(self):
        self._run = False
        if self._stop_hb:
            self._stop_hb.set()
        if getattr(self, "_ws", None):
            try:
                self._ws.close()
            except Exception:
                pass

    def _put_event(self, item):
        try:
            self.events.put_nowait(item)
        except queue.Full:
            try:
                self.events.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events.put_nowait(item)
            except queue.Full:
                pass

    def pop_event(self, timeout=0.5):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait_ready(self, timeout=15.0):
        return self.ready.wait(timeout)

    def _loop(self):
        backoff = 2.0
        while self._run and not self.fatal:
            try:
                self._connect()
                backoff = 2.0
            except _AuthInvalid:
                self.fatal = True
                log.error("Gateway menolak token (close 4004 / invalid session).")
                self.ready.set()
                return
            except Exception as exc:
                if not self._run:
                    return
                log.warning(
                    "gateway terputus: %s (%s), sambung ulang %.0fs",
                    type(exc).__name__,
                    exc,
                    backoff,
                )
                self.ready.clear()
                time.sleep(backoff)
                backoff = min(backoff * 2, 30.0)

    def _connect(self):
        self._stop_hb = threading.Event()
        ws = websocket.create_connection(GATEWAY_URL, timeout=30)
        self._ws = ws
        try:
            hello = self._recv_json(ws, timeout=15)
            if not hello or hello.get("op") != 10:
                raise RuntimeError("tidak menerima HELLO dari gateway")
            interval = float(hello["d"]["heartbeat_interval"]) / 1000.0
            stop_hb = self._stop_hb
            hb = threading.Thread(
                target=self._heartbeat, args=(ws, interval, stop_hb), daemon=True
            )
            hb.start()

            can_resume = bool(
                self.session_id and self.seq is not None and getattr(self, "can_resume", True)
            )
            if can_resume:
                log.info(
                    "gateway mencoba resume sesi %s (seq=%s)...",
                    mask(self.session_id),
                    self.seq,
                )
                ws.send(
                    json.dumps(
                        {
                            "op": 6,
                            "d": {
                                "token": self.token,
                                "session_id": self.session_id,
                                "seq": self.seq,
                            },
                        }
                    )
                )
            else:
                self.seq = None
                ws.send(
                    json.dumps(
                        {
                            "op": 2,
                            "d": {
                                "token": self.token,
                                "capabilities": 509,
                                "properties": {
                                    "os": "Windows",
                                    "browser": "Chrome",
                                    "device": "",
                                    "system_locale": "en-US",
                                    "browser_user_agent": (
                                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                                        "Chrome/131.0.0.0 Safari/537.36"
                                    ),
                                    "browser_version": "131.0.0.0",
                                    "os_version": "10",
                                },
                                "compress": False,
                            },
                        }
                    )
                )

            self.ready.clear()
            deadline = time.time() + 12.0
            ws.settimeout(2.0)
            while time.time() < deadline and not self.ready.is_set() and not self.fatal:
                payload = self._recv_json(ws, timeout=2.0)
                if payload is None:
                    continue
                self._handle(payload)
            if not self.ready.is_set() and not self.fatal:
                raise RuntimeError("timeout menunggu READY/RESUMED dari gateway")

            ws.settimeout(10.0)
            while self._run and not self.fatal:
                try:
                    payload = self._recv_json(ws, timeout=10.0)
                except websocket.WebSocketTimeoutException:
                    payload = None
                if payload is None:
                    continue
                self._handle(payload)
        finally:
            if self._stop_hb:
                self._stop_hb.set()
            self._ws = None
            try:
                ws.close()
            except Exception:
                pass

    def _heartbeat(self, ws, interval, stop_event=None):
        first = True
        while self._run and not self.fatal and not (stop_event and stop_event.is_set()):
            try:
                ws.send(json.dumps({"op": 1, "d": self.seq}))
            except Exception:
                return
            wait_time = 1.2 if first else interval * 0.9
            if stop_event and stop_event.wait(wait_time):
                return
            first = False

    @staticmethod
    def _recv_json(ws, timeout):
        try:
            ws.settimeout(timeout)
            raw = ws.recv()
        except websocket.WebSocketTimeoutException:
            return None
        except Exception as exc:
            status = getattr(ws, "close_status", None)
            if status == 4004:
                raise _AuthInvalid()
            raise RuntimeError(f"recv gagal: {exc}") from exc
        if raw in (None, ""):
            status = getattr(ws, "close_status", None)
            if status == 4004:
                raise _AuthInvalid()
            raise RuntimeError("gateway menutup koneksi")
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def _handle(self, payload):
        op = payload.get("op")
        if op == 11:
            return
        if op == 1:
            self.seq = payload.get("s") or self.seq
            return
        if op == 7:
            log.info("gateway meminta reconnect (op 7) -> menutup koneksi untuk resume...")
            raise RuntimeError("gateway requested reconnect (op 7)")
        if op == 9:
            resumable = bool(payload.get("d"))
            if not resumable:
                self.session_id = ""
                self.seq = None
            log.warning(
                "gateway opcode 9 (Invalid Session, resumable=%s), menghubungkan ulang...",
                resumable,
            )
            raise RuntimeError(f"gateway invalid session (op 9, resumable={resumable})")
        if op != 0:
            return
        self.seq = payload.get("s") or self.seq
        name = payload.get("t")
        data = payload.get("d")
        if not isinstance(data, dict):
            return

        if name == "RESUMED":
            self.ready.set()
            log.info("gateway resume berhasil: sesi %s dilanjutkan.", mask(self.session_id))
            return

        if name == "READY":
            user = data.get("user") or {}
            self.user_name = user.get("username", "")
            self.user_id = user.get("id", "")
            self.session_id = data.get("session_id", "")
            self.ready_data = data
            self.ready.set()
            log.info(
                "gateway siap: login sebagai %s (%s)",
                self.user_name,
                mask(self.user_id),
            )
            if callable(getattr(self, "on_session", None)):
                try:
                    self.on_session(self.session_id)
                except Exception:
                    pass
            return

        # Filter berdasarkan target channel
        d_chan = str(data.get("channel_id") or "")
        if self.channel_id and d_chan and d_chan != str(self.channel_id):
            return

        if name in ("INTERACTION_CREATE", "INTERACTION_MODAL_CREATE"):
            self._put_event(("interaction", data, time.time()))
            return

        if name in ("MESSAGE_CREATE", "MESSAGE_UPDATE"):
            kind = "message_new" if name == "MESSAGE_CREATE" else "message_edit"
            self._put_event((kind, data, time.time()))
            return


# =============================================================================
#  DEFINISI SCREEN & GRAF NAVIGASI
# =============================================================================
class Screen:
    def __init__(self, screen_id, match, buttons, patterns=None):
        self.id = screen_id
        self.match = [re.compile(p, re.IGNORECASE) for p in match]
        self.buttons = {key: label for key, label in buttons.items()}
        self._patterns = {
            key: re.compile(p, re.IGNORECASE) for key, p in (patterns or {}).items()
        }

    def matches(self, text):
        return any(rx.search(text) for rx in self.match)

    def pattern(self, logical):
        pat = self._patterns.get(logical)
        if pat:
            return pat
        return re.compile(re.escape(self.buttons[logical]), re.IGNORECASE)


SCREENS = [
    Screen(
        "home",
        [r"\bGrowcord[^\S\r\n]+Farm\b"],
        {
            "farm": "Farm",
            "ganti": "Ganti",
            "event": "Event",
            "toko": "Toko",
            "item": "Item",
            "profil": "Profil",
            "market": "Market",
            "guild": "Guild",
            "worlds": "Worlds",
        },
        {
            "farm": r"\bFarm\b",
            "toko": r"\bToko\b|\bShop\b",
            "item": r"\bItems?\b",
            "ganti": r"\bGanti\b|\bChange\b",
            "event": r"\bEvent\b",
            "profil": r"\bProfil\b|\bProfile\b",
            "market": r"\bMarket\b",
            "guild": r"\bGuild\b",
            "worlds": r"\bWorlds\b",
        },
    ),
    Screen(
        "fish",
        [r"Fishing\s*Rod", r"Fish\s*inventory"],
        {
            "back": "Back",
            "fish_start": "Fish (1 cast)",
            "bait": "Change Bait",
            "sell": "Sell Fish",
            "shop": "Shop",
            "inventory": "Inventory",
            "codex": "Fish Codex",
            "kembali": "Back",
        },
        {"back": r"\bBack\b", "kembali": r"\bBack\b", "fish_start": r"Fish\s*\(\s*1"},
    ),
    Screen(
        "toko",
        [r"Pilih\s*kategori\s*shop"],
        {
            "locks": "Lock",
            "farmable": "Farmable",
            "gacha": "Gacha",
            "alat": "Alat",
            "consumable": "Consumable",
            "item": "Item",
            "role": "Role",
            "aset": "Aset",
            "convert": "Convert",
            "traits": "Traits",
            "mutations": "Mutations",
            "kembali": "Kembali",
        },
        {
            "locks": r"\bLock\b",
            "item": r"\bItems?\b",
            "farmable": r"\bFarmables?\b",
            "consumable": r"\bConsumables?\b",
        },
    ),
    Screen(
        "consumables",
        [r"Item\s*•\s*(?:Consumables?|Habis\s*Pakai|Siap\s*Pakai)"],
        {
            "select_item": "Select Item",
            "use": "Use",
            "trade": "Trade",
            "back_item": "← Item",
            "back": "← Item",
            "tools": "Tools",
            "codex": "Item Codex",
        },
        {
            "use": r"\b(?:Use|Gunakan)\b",
            "select_item": r"Select\s*Item|Pilih\s*Item",
            "back_item": r"←\s*(?:Items?|Kembali|Back)\b|^\s*(?:Items?|Kembali|Back)\s*$",
            "back": r"←\s*(?:Items?|Kembali|Back)\b|^\s*(?:Items?|Kembali|Back)\s*$",
        },
    ),
    Screen(
        "items",
        [
            r"##\s*..\s*Item\s*•",
            r"##\s*🎒\s*Item\s*•",
            r"Item\s*•\s*(?:Terbatas|Custom|Unique|Normal)\s*Item",
            r"Item\s*•\s*(?:Terbatas|Custom|Unique|Normal)",
        ],
        {
            "consumable": "Habis Pakai",
            "back": "Kembali",
            "tools": "Tools",
            "ssu": "SSUs",
            "codex": "Item Codex",
        },
        {
            "consumable": r"\b(?:Consumables?|Habis\s*Pakai|Siap\s*Pakai)\b",
            "back": r"←?\s*(?:Kembali|Back)",
        },
    ),
    Screen(
        "shop_consumable",
        [
            r"Consumables?\s*Toko",
            r"Toko\s*Consumables?",
            r"Toko\s*(?:Habis|Siap)\s*Pakai",
            r"(?:Habis|Siap)\s*Pakai\s*Toko",
        ],
        {
            "beli_arroz": "Beli Arroz",
            "beli_benedict": "Beli Benedict",
            "kembali": "Kembali",
        },
        {
            "beli_arroz": r"(?:Beli|Buy)\s*Arroz",
            "beli_benedict": r"(?:Beli|Buy)\s*(?:Benedict|Eggs\s*Benedict)",
            "kembali": r"←?\s*(?:Kembali|Back)",
        },
    ),
    Screen(
        "shop_farmable",
        [
            r"Farmables?\s*(?:Toko|Shop)",
            r"Toko\s*Farmables?",
            r"Item\s*•\s*Farmables?",
            r"Pilih\s*farmable",
            r"Farmables?\s*Toko",
        ],
        {
            "select_item": "Select Item",
            "buy_max": "Buy Max",
            "kembali": "Kembali",
        },
        {
            "select_item": r"Select\s*(?:Item|Farmable)",
            "buy_max": r"\b(?:Buy|Beli)\s*Max\b|\bMax\b",
            "kembali": r"\bKembali\b|\bBack\b",
        },
    ),
    Screen(
        "locks",
        [r"Locks\s*Toko", r"Beli\s*WL", r"Pembelian\s*WL\s*bebas\s*pajak"],
        {
            "beli_wl": "Beli WL",
            "beli_dl": "Beli DL",
            "beli_bgl": "Beli BGL",
            "kembali": "Kembali",
        },
    ),
]

SOURCES = {s.id: s for s in SCREENS}

EDGES = [
    ("home", "toko", "toko"),
    ("toko", "locks", "locks"),
    ("locks", "kembali", "toko"),
    ("fish", "back", "home"),
    ("toko", "consumable", "shop_consumable"),
    ("shop_consumable", "kembali", "toko"),
    ("toko", "farmable", "shop_farmable"),
    ("shop_farmable", "kembali", "toko"),
    ("toko", "kembali", "home"),
    ("home", "item", "items"),
    ("items", "consumable", "consumables"),
    ("consumables", "back", "items"),
    ("consumables", "back_item", "items"),
    ("items", "back", "home"),
]


def route_steps(current_id, target_id):
    if current_id == target_id:
        return []
    parents = {}
    queue_ = deque([current_id])
    visited = {current_id}
    while queue_:
        node = queue_.popleft()
        for source, btn, nxt in EDGES:
            if source != node or nxt in visited:
                continue
            visited.add(nxt)
            parents[nxt] = (node, btn)
            if nxt == target_id:
                steps = []
                cursor = nxt
                while cursor != current_id:
                    cursor, back_btn = parents[cursor]
                    steps.append(back_btn)
                steps.reverse()
                return steps
            queue_.append(nxt)
    return None


# =============================================================================
#  BOT ENGINE
# =============================================================================
class Engine:
    def __init__(self, api, gateway, channel_id, guild_id=""):
        self.api = api
        self.gw = gateway
        self.channel_id = str(channel_id)
        self.guild_id = guild_id
        self.msg = None
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

    @staticmethod
    def _guess_modal(button_custom_id):
        parts = str(button_custom_id).split(":")
        if len(parts) >= 4 and parts[2] and "modal" not in parts[2]:
            parts[2] += "modal"
            guess = ":".join(parts)
            log.warning(
                "[modal] tidak terdeteksi realtime, pakai tebakan custom_id=%s "
                "field=amount (tebakan bot Growcord)",
                mask(guess),
            )
            return {"custom_id": guess, "id": "", "field_id": "amount", "max_length": None, "token": ""}
        return None

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
            return (
                f"{secs // 86400}d {(secs % 86400) // 3600}h {(secs % 3600) // 60}m"
            )
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
    def _is_growcord(msg, app_id=""):
        author = msg.get("author") or {}
        if app_id and str(author.get("id")) == str(app_id):
            return True
        if author.get("bot"):
            return True
        return author.get("username", "").lower() == "growcord"

    def abort_reason(self, text):
        low = (text or "").lower()
        for pattern in ABORT_PATTERNS:
            if pattern.lower() in low:
                return pattern
        return None

    def fetch_messages(self, limit=30):
        return self.api.get_messages(self.channel_id, limit=limit)

    def locate(self, msgs=None):
        docs = msgs if msgs is not None else self.fetch_messages()
        self._session_msgs = docs
        for msg in docs:
            if not self._is_growcord(msg, GROWCORD_APP_ID):
                continue
            text = self.message_text(msg)
            for screen in SCREENS:
                if screen.matches(text):
                    self.screen, self.msg = screen, msg
                    return screen, msg
        self.screen, self.msg = None, None
        return None, None

    def _match_button(self, msg, pattern):
        candidates = [
            c for c in self.message_buttons(msg) if pattern.search(c["label"])
        ]
        if not candidates:
            return None
        for comp in candidates:
            if not comp["disabled"]:
                return comp
        raise NavError(
            f'Tombol "{candidates[0]["label"]}" disabled (cooldown / tidak tersedia).'
        )

    def _click(self, msg, button, action_desc):
        log.info("[klik] %s", action_desc)
        if not button.get("custom_id"):
            raise NavError(f'Tombol "{button["label"]}" tidak memiliki custom_id.')
        try:
            return self.api.click_button(msg, button["custom_id"], self.guild_id)
        except ApiError:
            self.locate()
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
                f'Tombol "{spec}" tidak ditemukan di layar {screen_id}. Tombol terlihat: {found}'
            )
        self.last_click_id = button["custom_id"]
        return self._click(doc, button, f"[{screen_id}] {button['label']}")

    @staticmethod
    def _select_options(doc, custom_id):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == 3 and str(node.get("custom_id")) == str(
                    custom_id
                ):
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
        pick = None
        if options:
            pick = next(
                (
                    o
                    for o in options
                    if option_pat.search(o.get("label") or "")
                    or option_pat.search(o.get("value") or "")
                    or option_pat.search(o.get("description") or "")
                ),
                None,
            )
        if pick is None:
            listed = ", ".join(o.get("label", "?") for o in options) or "(kosong)"
            raise NavError(
                f"Opsi '{option_pat.pattern}' tidak ketemu pada select di {screen_id}. Opsi tersedia: {listed}"
            )
        log.info("[select] %s -> %s", spec, pick.get("label"))
        self.last_click_id = sel["custom_id"]
        return self.api.click_select(
            doc, sel["custom_id"], [pick.get("value")], self.guild_id
        )

    def wait_selected(self, nama_item, timeout=6.0):
        pat = re.compile(
            rf"(?:Dipilih|Selected)\s*:?.*?{re.escape(nama_item)}",
            re.IGNORECASE,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            docs = self.fetch_messages(30)
            for doc in docs:
                if not self._is_growcord(doc, GROWCORD_APP_ID):
                    continue
                text = self.message_text(doc)
                if pat.search(text):
                    self.screen, self.msg = self.locate(docs)
                    return True
            time.sleep(0.8)
        return False

    def _press_kembali(self):
        for doc in self._session_msgs:
            if not self._is_growcord(doc, GROWCORD_APP_ID):
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
            raise NavError(f"Layar tujuan '{screen_id}' tidak terdaftar")
        for _ in range(NAV_MAX_STEPS):
            screen, msg = self.locate()
            if screen is not None and screen.id == screen_id:
                return screen, msg
            if screen is None:
                log.info("layar tidak dikenali, mencoba tombol Kembali...")
                if not self._press_kembali():
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
                        "route %s -> %s tidak ketemu, coba Kembali",
                        screen.id,
                        screen_id,
                    )
                    if not self._press_kembali():
                        time.sleep(3.0)
            self.sleep_min_max(DELAY_NAV)
        screen, msg = self.locate()
        if screen is not None and screen.id == screen_id:
            return screen, msg
        where = screen.id if screen else "tidak dikenal"
        raise NavError(
            f"gagal sampai layar '{screen_id}' setelah {NAV_MAX_STEPS} langkah (posisi terakhir: {where})"
        )

    # -------------------------------------------------------------------------
    # PARSER DATA EMBED
    # -------------------------------------------------------------------------
    def read_gems(self, msgs=None):
        docs = (
            [msgs]
            if isinstance(msgs, dict)
            else (msgs if msgs is not None else self.fetch_messages(30))
        )
        for doc in docs:
            if not self._is_growcord(doc, GROWCORD_APP_ID):
                continue
            text = self.message_text(doc)
            wx = self._rx_gem.search(text)
            if wx:
                digits = re.sub(r"\D", "", wx.group(1))
                try:
                    return int(digits)
                except ValueError:
                    return None
        return None

    def read_autofarm_state(self, msgs=None):
        docs = (
            [msgs]
            if isinstance(msgs, dict)
            else (msgs if msgs is not None else self.fetch_messages(30))
        )
        for doc in docs:
            if not self._is_growcord(doc, GROWCORD_APP_ID):
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
        docs = (
            [msgs]
            if isinstance(msgs, dict)
            else (msgs if msgs is not None else self.fetch_messages(30))
        )
        for doc in docs:
            if not self._is_growcord(doc, GROWCORD_APP_ID):
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

            # 3. Indikasi habis
            if re.search(
                r"(?:Farmable\s*Saat\s*Ini|Current\s*Farmable|Farmable)\s*:\s*(?:Tidak\s*ada|None|-|Kosong|Empty)",
                text,
                re.I,
            ):
                return 0
            if re.search(r"Inventor(?:i|y)\s*:\s*\*{0,2}0\b", text, re.I):
                return 0
        return None

    def read_active_buffs(self, msgs=None):
        docs = (
            [msgs]
            if isinstance(msgs, dict)
            else (msgs if msgs is not None else self.fetch_messages(30))
        )
        for doc in docs:
            if not self._is_growcord(doc, GROWCORD_APP_ID):
                continue
            text = self.message_text(doc)
            if "Buff Aktif" not in text and "Aktif Buff" not in text:
                continue
            out = {}
            grab = False
            for line in text.split("\n"):
                head = line.strip()
                if not grab:
                    grab = bool(
                        re.match(r"[*# ]*(Buff\s*Aktif|Aktif\s*Buff)", head, re.I)
                    )
                    continue
                if not head.startswith("-"):
                    break
                body = head.lstrip("-").strip()
                rz = re.search(r"^(.*?)(?:\s*\u2022|\s+\|\s+|\s+for)\s*(.+)$", body)
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

    # -------------------------------------------------------------------------
    # GATEWAY WAIT & MODAL HELPERS
    # -------------------------------------------------------------------------
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
            if not self._is_growcord(data, GROWCORD_APP_ID):
                continue
            if msg_id and str(data.get("id")) != str(msg_id):
                continue
            inter = data.get("interaction") or {}
            user_id = (inter.get("user") or {}).get("id")
            if user_id and str(user_id) == str(self.gw.user_id):
                continue
            return data
        return None

    def capture_modal(self, timeout):
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
                body = data.get("data") or data
                fields = []

                def walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == 4 and node.get("custom_id"):
                            fields.append({
                                "custom_id": node["custom_id"],
                                "max_length": node.get("max_length"),
                            })
                        for v in node.values():
                            if isinstance(v, (dict, list)):
                                walk(v)
                    elif isinstance(node, list):
                        for it in node:
                            walk(it)

                walk(body.get("components") or [])
                if fields:
                    return {
                        "custom_id": body.get("custom_id") or "",
                        "id": data.get("id") or body.get("id") or "",
                        "field_id": fields[0]["custom_id"],
                        "max_length": fields[0].get("max_length"),
                        "token": data.get("token") or "",
                    }
            return None
        finally:
            for it in stashed:
                self.gw.events.put(it)

    def submit_modal_helper(self, modal, value):
        doc = self.msg or self.locate()[1]
        if doc is None:
            raise NavError("Pesan untuk submit modal tidak ditemukan")
        limit_val = value
        if isinstance(value, int) and modal.get("max_length"):
            try:
                max_len = int(modal["max_length"])
                if max_len > 0 and len(str(value)) > max_len:
                    limit_val = int("9" * max_len)
            except (ValueError, TypeError):
                pass
        log.info("[form] Mengisi %s=%s...", modal["field_id"], limit_val)
        return self.api.submit_modal(
            doc,
            modal["custom_id"],
            [(modal["field_id"], limit_val)],
            self.guild_id,
            interaction_token=modal.get("token") or "",
            modal_id=modal.get("id") or "",
        )

    # -------------------------------------------------------------------------
    # LOGIKA PEMBELIAN FARMABLE
    # -------------------------------------------------------------------------
    def buy_farmable(self, item_name=FARMABLE_ITEM):
        log.info("[farmable] Menuju Toko Farmable untuk membeli '%s'...", item_name)
        screen, msg = self.goto("shop_farmable")
        doc = msg or self.msg or self.locate()[1]
        if doc is None:
            raise NavError("Layar shop_farmable tidak ditemukan")

        clean_name = item_name.replace("'", "").replace("’", "")
        rx_item = re.compile(
            rf"{re.escape(item_name)}|{re.escape(clean_name)}|pot\s*o'?\s*gems",
            re.I,
        )

        try:
            self.click_screen_select("shop_farmable", "select_item", rx_item, msg=doc)
        except NavError as exc:
            log.warning(
                "[farmable] click_screen_select spesifik gagal (%s), mencari select...",
                exc,
            )
            sel = next(
                (c for c in self.message_buttons(doc) if c.get("type") == 3), None
            )
            if sel:
                options = self._select_options(doc, sel["custom_id"])
                pick = next(
                    (
                        o
                        for o in options
                        if rx_item.search(o.get("label", ""))
                        or rx_item.search(o.get("value", ""))
                    ),
                    None,
                )
                if pick:
                    log.info(
                        "[farmable] Memilih: %s (%s)",
                        pick.get("label"),
                        pick.get("value"),
                    )
                    self.api.click_select(
                        doc, sel["custom_id"], [pick["value"]], self.guild_id
                    )
                else:
                    raise NavError(
                        f"Opsi '{item_name}' tidak ditemukan di select shop_farmable"
                    )
            else:
                raise

        time.sleep(1.0)
        reply = self.wait_bot_reply(REPLY_TIMEOUT)
        target_msg = reply if reply is not None else (self.msg or self.locate()[1])

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
            raise NavError("Tombol 'Buy Max' tidak ditemukan di shop_farmable")

        log.info("[farmable] Menekan tombol [%s]...", btn_max["label"])
        self.api.click_button(target_msg, btn_max["custom_id"], self.guild_id)

        modal = self.capture_modal(1.5)
        if modal is None:
            modal = self._guess_modal(btn_max["custom_id"])
        if modal:
            log.info("[farmable] Form konfirmasi modal muncul, submit 'max'...")
            self.submit_modal_helper(modal, "max")

        reply_buy = self.wait_bot_reply(REPLY_TIMEOUT)
        if reply_buy:
            text = self.message_text(reply_buy)
            low = text.lower()
            if "cannot afford or store any more" in low or "tidak dapat menyimpan lebih banyak" in low:
                log.info("[farmable] ℹ️ Stok farmable sudah ada / penuh di inventori (cannot store any more). Kembali ke home...")
                self.goto("home")
                return

            reason = self.abort_reason(text)
            if reason:
                if any(w in low for w in ("tidak cukup", "insufficient", "kehabisan", "gems")):
                    raise GemsExhaustedError(f"Pembelian farmable ditolak (Gems habis): {reason}")
                raise NavError(f"Pembelian farmable ditolak: {reason}")
            log.info("[farmable] Balasan beli: %s", text.replace("\n", " ")[:140])

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

    # -------------------------------------------------------------------------
    # ANTI-AFK HANDLER
    # -------------------------------------------------------------------------
    def is_anti_afk_prompt(self, msg):
        if not msg or not isinstance(msg, dict):
            return False
        msg_chan = str(msg.get("channel_id") or "")
        if self.channel_id and msg_chan and msg_chan != str(self.channel_id):
            return False
        if not self._is_growcord(msg, GROWCORD_APP_ID):
            return False
        text = self.message_text(msg)
        if re.search(r"are\s*you\s*still\s*there\??", text, re.I):
            return True
        for b in self.message_buttons(msg):
            if re.search(r"yes[,\s]+keep\s+farming", b.get("label", ""), re.I):
                return True
        return False

    def handle_anti_afk(self, msg):
        buttons = self.message_buttons(msg)
        pat = re.compile(r"yes[,\s]+keep\s+farming", re.I)
        target = next(
            (
                b
                for b in buttons
                if pat.search(b.get("label", "")) and not b.get("disabled")
            ),
            None,
        )
        if target and target.get("custom_id"):
            log.info(
                "[anti-afk] ⚠️ DETEKSI: 'are you still there?' -> Mengklik [%s]...",
                target["label"],
            )
            # Berikan sedikit human delay agar natural
            delay_range = getattr(_cfg, "DELAY_ANTI_AFK", (1.2, 2.2)) if _cfg else (1.2, 2.2)
            time.sleep(random.uniform(*delay_range))
            try:
                self.api.click_button(msg, target["custom_id"], self.guild_id)
                self.afk_counter = getattr(self, "afk_counter", 0) + 1
                self.update_status_title()
                log.info(
                    "[anti-afk] ✅ BERHASIL KLIK [%s]! (Total ditangani: %d)",
                    target["label"],
                    self.afk_counter,
                )
                return True
            except Exception as exc:
                log.error(
                    "[anti-afk] Gagal mengklik [%s]: %s", target["label"], exc
                )
                return False
        return False

    def check_recent_anti_afk(self, limit=10):
        docs = self.fetch_messages(limit)
        for doc in docs:
            if self.is_anti_afk_prompt(doc):
                return self.handle_anti_afk(doc)
        return False


# =============================================================================
#  LOGIKA SISTEM BUFF (CLOVER, ARROZ, EGGS BENEDICT)
# =============================================================================
BUFF_ITEMS = [
    {"slug": "clover", "nama": "Lucky Clover", "beli": None},
    {"slug": "arroz", "nama": "Arroz Con Pollo", "beli": "beli_arroz"},
    {"slug": "eggs_benedict", "nama": "Eggs Benedict", "beli": "beli_benedict"},
]

RX_ALREADY = re.compile(
    r"timer\s*was\s*not\s*refreshed|sudah\s*aktif", re.IGNORECASE
)


def have_inventory_item(engine, nama):
    screen, doc = engine.goto("consumables")
    sel = engine._match_button(doc, screen.pattern("select_item"))
    if sel is None:
        log.info("[buff] inventory consumables kosong")
        return False
    options = engine._select_options(doc, sel["custom_id"])
    pat = re.compile(re.escape(nama), re.IGNORECASE)
    return any(pat.search(o.get("label") or "") for o in options)


def use_inventory_item(engine, nama, aktif):
    for k, sisa in (aktif or {}).items():
        if k.lower() == nama.lower():
            log.info("[buff] %s masih aktif (%s)", nama, engine.fmt_durasi(sisa))
            return True

    screen, doc = engine.goto("consumables")
    sel = engine._match_button(doc, screen.pattern("select_item"))
    if sel is None:
        log.warning("[buff] Dropdown item tidak ditemukan di inventory consumables")
        return False
    options = engine._select_options(doc, sel["custom_id"])
    rx = re.compile(re.escape(nama), re.IGNORECASE)
    pick = next(
        (
            o
            for o in options
            if rx.search(o.get("label") or "")
            or rx.search(o.get("value") or "")
            or rx.search(o.get("description") or "")
        ),
        None,
    )
    if pick is None:
        listed = ", ".join(o.get("label", "?") for o in options) or "(kosong)"
        log.warning(
            "[buff] Item '%s' tidak tersedia pada dropdown consumables (tersedia: %s)",
            nama,
            listed,
        )
        return False

    try:
        engine.click_screen_select("consumables", "select_item", rx, msg=doc)
    except NavError as exc:
        log.warning("[buff] Gagal memilih '%s' di select: %s", nama, exc)
        return False

    if not engine.wait_selected(nama):
        log.warning("[buff] Timeout konfirmasi terpilihnya '%s'", nama)
        return False

    try:
        engine.click_screen_button("consumables", "use")
    except NavError as exc:
        log.warning("[buff] Gagal menekan tombol 'Use' untuk '%s': %s", nama, exc)
        return False

    modal = engine.capture_modal(1.5)
    if modal:
        try:
            engine.submit_modal_helper(modal, 1)
        except Exception as exc:
            log.warning("[buff] Gagal submit modal form use '%s': %s", nama, exc)

    reply = engine.wait_bot_reply(REPLY_TIMEOUT)
    if reply is None:
        log.warning("[buff] balasan use %s tidak terdeteksi", nama)
        return False
    text = engine.message_text(reply)
    if RX_ALREADY.search(text):
        log.info(
            "[buff] %s: sudah aktif (stok terpakai tanpa refresh timer)", nama
        )
        return True
    reason = engine.abort_reason(text)
    if reason:
        log.warning("[buff] use %s ditolak bot: %s", nama, reason)
        return False
    return True


def has_buff(aktif_dict, buff_name):
    if not aktif_dict:
        return False
    target = buff_name.lower()
    for k, sisa in aktif_dict.items():
        if target in k.lower():
            if isinstance(sisa, (int, float)):
                return sisa > 0
            return True
    return False


def check_and_apply_buffs(engine):
    log.info("[buff] Memeriksa efek buff aktif...")
    try:
        engine.goto("home")
    except NavError as exc:
        log.warning("[buff] Gagal navigasi ke home saat cek buff: %s", exc)
        return
    aktif = engine.read_active_buffs()

    for item in BUFF_ITEMS:
        nama, tombol_beli = item["nama"], item["beli"]

        # Jika Lucky Clover dan sudah pernah dicek di awal tanpa sisa stok, lewati jika tidak aktif
        if tombol_beli is None and (getattr(engine, "clover_checked", False) is True) and (getattr(engine, "clover_has_more", False) is not True):
            if not has_buff(aktif, nama):
                log.info(
                    "[buff] %s tidak aktif dan tidak dijual di Toko, lewati...",
                    nama,
                )
                continue

        # Cek apakah buff masih aktif
        if has_buff(aktif, nama):
            sisa = next(
                (
                    sisa
                    for k, sisa in aktif.items()
                    if nama.lower() in k.lower()
                ),
                0,
            )
            log.info(
                "[buff] %s masih aktif (%s), lewati",
                nama,
                engine.fmt_durasi(sisa) if sisa else "aktif",
            )
            continue

        log.info("[buff] Memproses aktivasi %s...", nama)

        # Cek apakah item ada di inventory
        have_item = False
        try:
            have_item = have_inventory_item(engine, nama)
        except NavError as exc:
            log.warning("[buff] NavError saat cek inventory %s: %s", nama, exc)

        if not have_item:
            log.info("[buff] %s tidak tersedia di inventory", nama)
            if tombol_beli is None:
                log.warning(
                    "[buff] %s tidak dijual di Toko Consumables, lewati...",
                    nama,
                )
                engine.clover_checked = True
                engine.clover_has_more = False
                continue

            # Beli di Toko Consumables (hanya Arroz & Eggs Benedict)
            log.info(
                "[buff] Membeli %s x5 di Toko Consumables...",
                nama,
            )
            bought_ok = False
            for buy_attempt in range(1, 3):
                try:
                    engine.goto("shop_consumable")
                    engine.click_screen_button("shop_consumable", tombol_beli)
                    modal = engine.capture_modal(MODAL_TIMEOUT)
                    if modal is None and hasattr(engine, "_guess_modal"):
                        modal = engine._guess_modal(getattr(engine, "last_click_id", ""))
                    if modal:
                        engine.submit_modal_helper(modal, 5)
                        reply = engine.wait_bot_reply(REPLY_TIMEOUT)
                        if reply is not None:
                            reason = engine.abort_reason(engine.message_text(reply))
                            if reason:
                                low = reason.lower()
                                if any(w in low for w in ("tidak cukup", "insufficient", "kehabisan", "gems")):
                                    raise GemsExhaustedError(f"Pembelian buff {nama} ditolak (Gems habis): {reason}")
                                log.warning("[buff] Pembelian %s ditolak: %s", nama, reason)
                                break
                        bought_ok = True
                        break
                    else:
                        log.warning(
                            "[buff] Modal form pembelian %s tidak muncul (percobaan %d)",
                            nama,
                            buy_attempt,
                        )
                        time.sleep(2.0)
                except (NavError, ApiError) as exc:
                    log.warning("[buff] Kendala saat membeli %s: %s", nama, exc)
                    time.sleep(2.0)

            if not bought_ok:
                log.warning(
                    "[buff] Tidak berhasil membeli %s di Toko Consumables. Menunda aktivasi ke siklus berikutnya.",
                    nama,
                )
                continue

        # Gunakan item dari inventory
        used = False
        for attempt in (1, 2):
            try:
                if use_inventory_item(engine, nama, engine.read_active_buffs()):
                    used = True
                    log.info("[buff] ✅ %s berhasil digunakan!", nama)
                    break
            except (NavError, ApiError) as exc:
                log.warning(
                    "[buff] Kendala saat menggunakan %s (percobaan %d): %s",
                    nama,
                    attempt,
                    exc,
                )
            log.warning(
                "[buff] Gagal menggunakan %s (percobaan %d), ulangi...",
                nama,
                attempt,
            )
            time.sleep(2.0)

        if not used:
            log.warning("[buff] Tidak dapat mengaktifkan %s pada siklus ini", nama)

    try:
        engine.goto("home")
    except Exception:
        pass
    log.info("[buff] Pengecekan buff selesai.")


# =============================================================================
#  PENGATURAN STATUS AUTO FARM (OFF -> ON)
# =============================================================================
def set_autofarm_state(engine, desired="ON"):
    try:
        screen, msg = engine.goto("home")
    except (NavError, ApiError) as exc:
        log.warning("Gagal navigasi ke home saat set autofarm: %s", exc)
        return False
    current = engine.read_autofarm_state([msg])
    if current is None:
        current = engine.read_autofarm_state()

    log.info("Status Auto Farm di main menu: %s -> target %s", current, desired)
    if current == desired:
        log.info("Auto Farm sudah %s, tidak ada aksi.", desired)
        return True

    for attempt in range(1, 6):
        try:
            screen, msg = engine.goto("home")
        except (NavError, ApiError):
            pass
        current = engine.read_autofarm_state([msg] if msg else None)
        if current == desired:
            log.info("✅ Auto Farm sekarang: %s", desired)
            return True
        try:
            engine.click_screen_button("home", "farm", msg=msg)
        except (NavError, ApiError) as exc:
            if "disabled" in str(exc).lower():
                log.warning(
                    "Percobaan %d: tombol Farm disabled (cooldown server), tunggu 3.5s...",
                    attempt,
                )
                time.sleep(3.5)
                continue
            log.warning("Percobaan %d: gagal klik tombol Farm: %s", attempt, exc)
            time.sleep(2.0)
            continue
        time.sleep(1.5)
        _, fresh_msg = engine.locate()
        new_state = engine.read_autofarm_state([fresh_msg] if fresh_msg else None)
        if new_state == desired:
            log.info("✅ Auto Farm sekarang: %s", desired)
            return True
        log.warning(
            "Percobaan %d: status belum %s (terdeteksi: %s), tunggu...",
            attempt,
            desired,
            new_state,
        )
        time.sleep(2.0)
    log.warning("Auto Farm belum berubah ke %s setelah 5 percobaan, akan dicoba kembali nanti", desired)
    return False


# =============================================================================
#  RANGKAIAN PERSIAPAN LENGKAP AUTOFARM
# =============================================================================
def prepare_autofarm(engine):
    """1. Cek stock farmable di main menu. Jika <= 0 -> beli Pot o' Gems (Buy Max) -> Home
    2. Cek Lucky Clover sekali saja saat startup (jika tidak ada di inventory, lewati).
    3. Cek buff Arroz Con Pollo & Eggs Benedict:
       - Jika buff sudah aktif dan stok farmable > 0 -> langsung klik Farm (jika OFF).
       - Jika buff habis -> gunakan/beli -> Home.
    4. Pastikan Auto Farm ON di main menu.
    """
    log.info("================ PERSIAPAN AUTOFARM ================")
    screen, msg = engine.goto("home")

    # 1. Cek Lucky Clover 1x di awal atau saat punya stok tersisa
    if not getattr(engine, "clover_checked", False) or getattr(engine, "clover_has_more", False):
        aktif_init = engine.read_active_buffs(msg)
        if not has_buff(aktif_init, "Lucky Clover"):
            log.info("[autofarm] Memeriksa stok Lucky Clover di inventory...")
            if have_inventory_item(engine, "Lucky Clover"):
                use_inventory_item(engine, "Lucky Clover", aktif_init)
            else:
                log.info("[autofarm] Lucky Clover tidak ada di inventory, dilewati.")
                engine.clover_has_more = False
            screen, msg = engine.goto("home")
        engine.clover_checked = True

    # 2. Cek stock farmable & buff saat ini di main menu
    stock = engine.read_farmable_stock(msg)
    aktif = engine.read_active_buffs(msg)
    state = engine.read_autofarm_state([msg])

    if stock is not None:
        log.info("[autofarm] Stock farmable saat ini: %s block", engine.fmt_int(stock))
    else:
        log.warning("[autofarm] Stock farmable tidak terbaca spesifik dari embed home")

    arroz_ok = has_buff(aktif, "Arroz Con Pollo")
    benedict_ok = has_buff(aktif, "Eggs Benedict")
    buffs_ok = arroz_ok and benedict_ok
    stock_ok = (stock is None or stock > 0)

    log.info(
        "[autofarm] Status: Stock OK=%s | Buffs Aktif=%s (Arroz=%s, Benedict=%s) | Auto Farm=%s",
        stock_ok,
        buffs_ok,
        arroz_ok,
        benedict_ok,
        state,
    )

    # KONDISI UTAMA:
    # "Jika buff udah ada, dan Farmable saat ininya belum 0, tinggal pencet Farm aja"
    if stock_ok and buffs_ok:
        log.info(
            "[autofarm] ✅ Buff sudah aktif dan stok farmable belum 0! Cukup pastikan Auto Farm: ON."
        )
        if state != "ON":
            log.info("[autofarm] Menyalakan Auto Farm (OFF -> ON)...")
            set_autofarm_state(engine, "ON")
        else:
            log.info("[autofarm] Auto Farm sudah aktif (ON).")
        log.info("====================================================")
        return

    # Jika stok habis (<= 0)
    if stock is not None and stock <= 0:
        log.warning(
            "[autofarm] Stock farmable KOSONG (%s)! Membeli '%s' (Buy Max)...",
            stock,
            FARMABLE_ITEM,
        )
        engine.buy_farmable(FARMABLE_ITEM)
        screen, msg = engine.goto("home")
        stock = engine.read_farmable_stock(msg)
        log.info("[autofarm] Stock farmable setelah beli: %s", stock)

    # Jika buff habis / belum aktif
    if not buffs_ok:
        log.info("[autofarm] Menjalankan pemakaian / pembelian buff...")
        check_and_apply_buffs(engine)
        screen, msg = engine.goto("home")

    # Pastikan Auto Farm ON
    state = engine.read_autofarm_state([msg])
    log.info("[autofarm] Status Auto Farm: %s", state)
    if state != "ON":
        log.info("[autofarm] Menyalakan Auto Farm (OFF -> ON)...")
        set_autofarm_state(engine, "ON")
    else:
        log.info("[autofarm] Auto Farm sudah aktif (ON).")
    log.info("====================================================")


# =============================================================================
#  LOOP UTAMA STANDBY / IDLE MONITORING (ANTI-AFK REALTIME)
# =============================================================================
def run_autofarm_system(engine):
    log.info("Memulai Sistem Auto Farm Terpadu (Single Script)...")

    # Cek apakah ada prompt anti-AFK lama
    engine.check_recent_anti_afk()

    # Jalankan persiapan lengkap awal
    prepare_autofarm(engine)

    # Kuras event Gateway yang menumpuk secara aman (Anti-AFK tidak terbuang)
    if hasattr(engine, "safe_drain_events"):
        engine.safe_drain_events()
    else:
        while engine.gw.pop_event(timeout=0) is not None:
            pass

    log.info(
        "[autofarm] ✅ Semua persiapan selesai! Masuk mode STANDBY MONITORING."
    )
    log.info(
        "[autofarm] 📡 Mendengarkan pesan Discord Gateway secara realtime:"
    )
    log.info(
        "  - Anti-AFK: jika bot kirim 'are you still there?' -> auto click 'Yes, keep farming'"
    )
    log.info(
        "  - Auto-Restock: jika farmable habis (0) -> otomatis beli Pot O' Gems"
    )
    log.info(
        "  - Auto-Rebuff: jika buff habis -> otomatis re-buff"
    )
    log.info("Tekan Ctrl+C di terminal kapan saja untuk berhenti.\n")

    if hasattr(engine, "update_status_title"):
        engine.update_status_title()

    last_periodic_check = time.time()

    try:
        while True:
            # Jika gateway mengalami error fatal (token revoked/invalid), hentikan loop
            if getattr(engine.gw, "fatal", False) is True:
                raise AuthError("Gateway fatal: token ditolak atau sesi tidak valid.")

            # Pastikan gateway siap
            if hasattr(engine.gw, "ready") and not engine.gw.ready.is_set():
                time.sleep(1.0)
                continue

            # Ambil event dari Gateway realtime
            event = engine.gw.pop_event(timeout=1.0)
            if event is not None:
                kind, data, _ts = event
                if kind in ("message_new", "message_edit"):
                    # Verifikasi pesan berasal dari target channel bot
                    msg_chan = str(data.get("channel_id") or "")
                    if engine.channel_id and msg_chan and msg_chan != str(engine.channel_id):
                        continue

                    # 1. Deteksi tantangan Anti-AFK
                    if engine.is_anti_afk_prompt(data):
                        engine.handle_anti_afk(data)
                        if hasattr(engine, "safe_drain_events"):
                            engine.safe_drain_events()
                        else:
                            while engine.gw.pop_event(timeout=0) is not None:
                                pass
                        continue

                    # 2. Pantau update embed Growcord Farm
                    if engine._is_growcord(data, GROWCORD_APP_ID):
                        text = engine.message_text(data)
                        if "Growcord Farm" in text:
                            stock = engine.read_farmable_stock([data])
                            aktif = engine.read_active_buffs([data])
                            current_state = engine.read_autofarm_state([data])

                            arroz_ok = has_buff(aktif, "Arroz Con Pollo")
                            benedict_ok = has_buff(aktif, "Eggs Benedict")

                            # Kasus A: Stok farmable habis (0 block)
                            if stock is not None and stock <= 0:
                                log.warning(
                                    "[autofarm] Terdeteksi stock farmable HABIS (%s)! Membeli '%s' (Buy Max)...",
                                    stock,
                                    FARMABLE_ITEM,
                                )
                                try:
                                    engine.buy_farmable(FARMABLE_ITEM)
                                    screen, msg = engine.goto("home")
                                    if engine.read_autofarm_state([msg]) != "ON":
                                        set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat restock farmable: %s", exc)
                                    try:
                                        engine.goto("home")
                                    except Exception:
                                        pass
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                last_periodic_check = time.time()
                                continue

                            # Kasus B: Buff habis (hilang dari Buff Aktif di embed)
                            has_buff_header = ("Buff Aktif" in text) or ("Aktif Buff" in text)
                            if has_buff_header and (not arroz_ok or not benedict_ok):
                                log.warning(
                                    "[autofarm] Buff terdeteksi habis (Arroz: %s, Benedict: %s)! Menjalankan re-buff...",
                                    arroz_ok,
                                    benedict_ok,
                                )
                                try:
                                    check_and_apply_buffs(engine)
                                    screen, msg = engine.goto("home")
                                    if engine.read_autofarm_state([msg]) != "ON":
                                        set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat re-buff: %s", exc)
                                    try:
                                        engine.goto("home")
                                    except Exception:
                                        pass
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                last_periodic_check = time.time()
                                continue

                            # Kasus C: Auto Farm OFF padahal stok masih ada dan buff masih aktif
                            if current_state == "OFF" and (stock is None or stock > 0) and arroz_ok and benedict_ok:
                                log.info(
                                    "[autofarm] Auto Farm berstatus OFF tapi stok & buff masih aktif. Menyalakan kembali (klik Farm)..."
                                )
                                try:
                                    set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat menyalakan Auto Farm: %s", exc)
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                continue

            # Pengecekan berkala (heartbeat)
            if time.time() - last_periodic_check >= CHECK_INTERVAL:
                last_periodic_check = time.time()
                log.info(
                    "[autofarm] Heartbeat check (interval %ds)...",
                    CHECK_INTERVAL,
                )
                try:
                    screen, msg = engine.goto("home")
                    stock = engine.read_farmable_stock(msg)
                    aktif = engine.read_active_buffs(msg)
                    current_state = engine.read_autofarm_state([msg])

                    arroz_ok = has_buff(aktif, "Arroz Con Pollo")
                    benedict_ok = has_buff(aktif, "Eggs Benedict")

                    log.info(
                        "[autofarm] Heartbeat status: Stock=%s | Arroz=%s | Benedict=%s | Auto Farm=%s",
                        stock,
                        arroz_ok,
                        benedict_ok,
                        current_state,
                    )

                    if stock is not None and stock <= 0:
                        log.warning("[autofarm] Heartbeat: Stock habis! Membeli ulang...")
                        engine.buy_farmable(FARMABLE_ITEM)
                        screen, msg = engine.goto("home")

                    if not arroz_ok or not benedict_ok:
                        log.warning(
                            "[autofarm] Heartbeat: Buff habis! Menjalankan re-buff..."
                        )
                        check_and_apply_buffs(engine)
                        screen, msg = engine.goto("home")

                    if engine.read_autofarm_state([msg]) != "ON":
                        set_autofarm_state(engine, "ON")

                    if hasattr(engine, "update_status_title"):
                        engine.update_status_title(stock=stock, buffs=aktif, state=current_state)
                except Exception as exc:
                    log.warning("[autofarm] Kendala saat heartbeat check: %s", exc)
                    try:
                        engine.goto("home")
                    except Exception:
                        pass

                if hasattr(engine, "safe_drain_events"):
                    engine.safe_drain_events()
                else:
                    while engine.gw.pop_event(timeout=0) is not None:
                        pass

    except KeyboardInterrupt:
        log.warning("[autofarm] Dihentikan oleh pengguna (Ctrl+C)")
        raise


# =============================================================================
#  ENTRYPOINT UTAMA
# =============================================================================
def main():
    setup_logging()

    if not TOKEN or "ISI_" in TOKEN:
        log.error("DISCORD_TOKEN belum diisi!")
        sys.exit(1)
    if not CHANNEL_ID.isdigit():
        log.error("GROWCORD_CHANNEL (CHANNEL_ID) belum diisi angka!")
        sys.exit(1)

    api = Api(TOKEN, USER_AGENT)
    gw = Gateway(TOKEN)
    api._session_provider = lambda: gw.session_id if gw else ""
    gw.on_session = lambda sid: setattr(api, "session_id", sid)
    engine = Engine(api, gw, CHANNEL_ID)

    log.info("Menghubungkan ke Gateway Discord...")
    gw.start()

    consecutive_errors = 0
    try:
        while True:
            try:
                if not gw.wait_ready(30):
                    log.warning(
                        "Gateway tidak READY dalam 30 detik. Menunggu sambungan ulang..."
                    )
                    time.sleep(5.0)
                    continue
                if gw.fatal:
                    raise AuthError("Token ditolak oleh gateway (invalid token/session).")

                log.info("Login sukses sebagai: %s", gw.user_name)
                if gw.session_id:
                    api.session_id = gw.session_id
                    log.info("Session ID terpasang.")

                # Ambil info thread/channel
                try:
                    info = api.channel_info(CHANNEL_ID)
                    engine.guild_id = info.get("guild_id", "")
                    log.info("Channel tujuan: %s", info.get("name", CHANNEL_ID))
                except ApiError as exc:
                    log.warning("Gagal membaca channel info: %s", exc)

                consecutive_errors = 0
                # Jalankan sistem autofarm lengkap
                run_autofarm_system(engine)

            except KeyboardInterrupt:
                raise
            except GemsExhaustedError as exc:
                set_console_title("Growcord Bot [BERHENTI - GEMS HABIS]")
                log.critical(
                    "\n======================================================\n"
                    " [KRITIS] GEMS HABIS / TIDAK MENCUKUPI!\n"
                    " %s\n"
                    " Bot dihentikan sesuai instruksi pengguna.\n"
                    " Silakan isi Gems akun Anda lalu jalankan ulang bot.\n"
                    "======================================================",
                    exc,
                )
                break
            except AuthError as exc:
                log.error("Autentikasi gagal / Token ditolak: %s", exc)
                break
            except Exception as exc:
                consecutive_errors += 1
                delay = min(10.0 * consecutive_errors, 60.0)
                log.error(
                    "[24/7 Supervisor] Terjadi kesalahan (%s): %s. "
                    "Memulai pemulihan otomatis dalam %.0fs...",
                    type(exc).__name__,
                    exc,
                    delay,
                )
                try:
                    engine.goto("home")
                except Exception:
                    pass
                time.sleep(delay)

    except KeyboardInterrupt:
        log.warning("Dihentikan pengguna (Ctrl+C)")
    finally:
        gw.stop()
        log.info("Gateway dimatikan. Selesai.")


if __name__ == "__main__":
    main()
