import json
import logging
import queue
import threading
import time

import websocket

log = logging.getLogger("growcord.gateway")

GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"


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

    def joined_threads(self):
        result = []
        for guild in self.ready_data.get("guilds") or []:
            guild_name = guild.get("name") or guild.get("id", "?")
            for thread in guild.get("threads") or []:
                result.append(
                    {
                        "guild": guild_name,
                        "id": str(thread.get("id")),
                        "name": thread.get("name", ""),
                        "parent": thread.get("parent_id", ""),
                    }
                )
        return result

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
                log.error(
                    "Gateway menolak token (invalid session / close 4004). "
                    "Token kemungkinan salah, expired, atau akun logout."
                )
                self.ready.set()
                return
            except Exception as exc:
                if not self._run:
                    return
                log.warning("gateway terputus: %s (%s), sambung ulang %.0fs", type(exc).__name__, exc, backoff)
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
            hb = threading.Thread(target=self._heartbeat, args=(ws, interval, stop_hb), daemon=True)
            hb.start()

            can_resume = bool(self.session_id and self.seq is not None and getattr(self, "can_resume", True))
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
                raise RuntimeError("timeout menunggu READY dari gateway")

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
            log.info("gateway siap: login sebagai %s (%s)", self.user_name, mask(self.user_id))
            if callable(getattr(self, "on_session", None)):
                try:
                    self.on_session(self.session_id)
                except Exception:
                    pass
            return

        # Filter berdasarkan channel_id jika telah dikonfigurasi
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


class _AuthInvalid(Exception):
    pass


def mask(value):
    value = str(value or "")
    if len(value) <= 12:
        return value
    return value[:6] + "..." + value[-4:]
