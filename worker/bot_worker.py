import logging
import os
import queue
import re
import sys
import threading
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from autofarm import (
    Api,
    Gateway,
    Engine,
    ApiError,
    AuthError,
    NavError,
    GemsExhaustedError,
    prepare_autofarm,
    set_autofarm_state,
    has_buff,
    GROWCORD_APP_ID,
    USER_AGENT,
    FARMABLE_ITEMS,
)
from notifier import DiscordNotifier
from state_store import load_account_state, save_account_state
from supabase_client import SupabaseClient

log = logging.getLogger("growcord.worker")


def parse_duration_to_sec(dur_val: Any) -> int:
    """Mengonversi format durasi detik (int) atau string '1h 20m', '45m 10s' ke total detik."""
    if dur_val is None:
        return 0
    if isinstance(dur_val, (int, float)):
        return int(dur_val)
    dur_str = str(dur_val).strip()
    if not dur_str:
        return 0
    total = 0
    m_h = re.search(r"(\d+)\s*(?:h|j|jam)", dur_str, re.I)
    if m_h:
        total += int(m_h.group(1)) * 3600
    m_m = re.search(r"(\d+)\s*(?:m|menit)", dur_str, re.I)
    if m_m:
        total += int(m_m.group(1)) * 60
    m_s = re.search(r"(\d+)\s*(?:s|detik)", dur_str, re.I)
    if m_s:
        total += int(m_s.group(1))
    return total


class BotWorker(threading.Thread):
    def __init__(
        self,
        account_id: str,
        label: str,
        token: str,
        channel_id: str,
        farmable_item: str = "Pot O' Gems",
        gem_floor: int = 2000,
        supabase: Optional[SupabaseClient] = None,
        notifier: Optional[DiscordNotifier] = None,
    ):
        super().__init__(name=f"Worker-{label}", daemon=True)
        self.account_id = account_id
        self.label = label
        self.token = token
        self.channel_id = str(channel_id)
        self.farmable_item = farmable_item or "Pot O' Gems"
        self.gem_floor = gem_floor

        self.supabase = supabase or SupabaseClient()
        self.notifier = notifier or DiscordNotifier()

        self._running = False
        self._paused = False
        self.command_queue: queue.Queue = queue.Queue()

        self.api: Optional[Api] = None
        self.gw: Optional[Gateway] = None
        self.engine: Optional[Engine] = None

        # Telemetri cache: langsung muat dari local file cache / fallback Supabase
        cached = load_account_state(
            account_id=self.account_id,
            fallback_fetcher=lambda: self.supabase.get_latest_metrics(self.account_id) if self.supabase else None,
        )
        self.last_gems = int(cached.get("gems_balance", 0))
        self.last_stock = int(cached.get("stock_remaining", 0))
        self.last_buff_clover = int(cached.get("buff_clover_sec", 0))
        self.last_buff_arroz = int(cached.get("buff_arroz_sec", 0))
        self.last_buff_benedict = int(cached.get("buff_benedict_sec", 0))

    def stop(self):
        """Meminta worker berhenti secara tertib."""
        log.info("[%s] Menghentikan worker bot...", self.label)
        self._running = False
        self.command_queue.put({"command": "STOP"})
        if self.gw:
            try:
                self.gw.stop()
            except Exception:
                pass

    def pause(self):
        self._paused = True
        self.command_queue.put({"command": "PAUSE"})

    def resume(self):
        self._paused = False
        self.command_queue.put({"command": "START"})

    def update_config(
        self,
        farmable_item: Optional[str] = None,
        gem_floor: Optional[int] = None,
        label: Optional[str] = None,
    ):
        """Hot-reload konfigurasi tanpa memutus sesi Discord Gateway."""
        if farmable_item is not None and farmable_item != self.farmable_item:
            old_item = self.farmable_item
            self.farmable_item = farmable_item
            if self.engine:
                self.engine.farmable_item = farmable_item
            log.info("[%s] ⚡ Hot-reload farmable_item: '%s' -> '%s'", self.label, old_item, self.farmable_item)
        if gem_floor is not None and int(gem_floor) != self.gem_floor:
            old_floor = self.gem_floor
            self.gem_floor = int(gem_floor)
            log.info("[%s] ⚡ Hot-reload gem_floor: %d -> %d", self.label, old_floor, self.gem_floor)
        if label is not None and label != self.label:
            self.label = label

    def queue_command(self, cmd_dict: Dict[str, Any]):
        self.command_queue.put(cmd_dict)

    def run(self):
        self._running = True
        log.info("[%s] Memulai inisialisasi koneksi Discord Gateway...", self.label)

        self.api = Api(self.token, USER_AGENT)
        self.gw = Gateway(self.token)
        self.api._session_provider = lambda: self.gw.session_id if self.gw else ""
        self.gw.on_session = lambda sid: setattr(self.api, "session_id", sid)
        self.engine = Engine(self.api, self.gw, self.channel_id, farmable_item=self.farmable_item)

        try:
            self.gw.start()
            # Berikan waktu hingga 60 detik untuk menerima payload READY & GUILD_CREATE dari Discord
            if not self.gw.wait_ready(60):
                if self.gw.ready.is_set():
                    log.info("[%s] Gateway siap sesaat sebelum batas timeout.", self.label)
                else:
                    err_msg = "Gateway tidak READY dalam 60 detik (koneksi terputus/timeout)"
                    self._handle_critical_error(err_msg)
                    return

            if getattr(self.gw, "fatal", False):
                err_msg = "Token ditolak oleh Discord Gateway (401 Unauthorized / Token Expired)"
                self._handle_critical_error(err_msg)
                return

            log.info("[%s] Berhasil login sebagai: %s", self.label, self.gw.user_name)

            # Ambil info channel
            try:
                info = self.api.channel_info(self.channel_id)
                self.engine.guild_id = info.get("guild_id", "")
            except Exception as exc:
                log.warning("[%s] Gagal mengambil info channel %s: %s", self.label, self.channel_id, exc)

            # Perbarui status ke ACTIVE di Supabase
            self.supabase.update_account_status(self.account_id, "ACTIVE")
            self.supabase.log_event(
                self.account_id,
                "SYSTEM",
                "INFO",
                f"Bot '{self.label}' berhasil terhubung dan siap autofarm.",
            )
            self.notifier.send_alert(
                "[INFO] Bot Worker Started",
                f"Bot `{self.label}` berhasil login ke Gateway Discord.",
                "INFO",
                self.label,
                {"Channel": self.channel_id},
            )

            # Persiapan awal farm
            try:
                prepare_autofarm(self.engine, farmable_item=self.farmable_item)
            except Exception as exc:
                log.warning("[%s] Persiapan awal autofarm ada kendala: %s", self.label, exc)

            # Masuk ke loop pemantauan & event listener
            self._main_monitoring_loop()

        except Exception as exc:
            log.exception("[%s] Kesalahan tak terduga pada worker: %s", self.label, exc)
            self._handle_critical_error(str(exc))
        finally:
            log.info("[%s] Worker thread selesai.", self.label)
            if self.gw:
                try:
                    self.gw.stop()
                except Exception:
                    pass

    def _main_monitoring_loop(self):
        last_telemetry_time = time.time()
        consecutive_gw_errors = 0

        while self._running:
            now = time.time()

            # 1. Proses antrean perintah remote dari Web Dashboard
            while not self.command_queue.empty():
                try:
                    cmd_obj = self.command_queue.get_nowait()
                    self._execute_remote_command(cmd_obj)
                except queue.Empty:
                    break

            # Cek status fatal gateway
            if getattr(self.gw, "fatal", False):
                self._handle_critical_error("Token Discord expired atau ditolak saat sesi berlangsung (401).")
                break

            # 2. Ambil event Gateway realtime
            try:
                event = self.gw.pop_event(timeout=1.0)
                if event is not None:
                    consecutive_gw_errors = 0
                    kind, data, _ts = event
                    if kind in ("message_new", "message_edit"):
                        msg_chan = str(data.get("channel_id") or "")
                        if self.channel_id and msg_chan and msg_chan != self.channel_id:
                            continue

                        # A. Deteksi & Jawab Anti-AFK
                        if self.engine.is_anti_afk_prompt(data):
                            self._handle_anti_afk_challenge(data)
                            continue

                        # B. Baca pembaruan Embed Growcord Farm
                        if self.engine._is_growcord(data, GROWCORD_APP_ID):
                            self._process_growcord_embed(data)

            except Exception as exc:
                consecutive_gw_errors += 1
                log.warning("[%s] Gateway pop_event error (%d/5): %s", self.label, consecutive_gw_errors, exc)
                if consecutive_gw_errors >= 5:
                    self._handle_critical_error("Koneksi Discord Gateway terputus lebih dari 5 kali berturut-turut.")
                    break

            # 3. Laporkan telemetri & heartbeat berkala setiap 30 detik
            if now - last_telemetry_time >= 30.0:
                self._send_telemetry_update()
                last_telemetry_time = now

    def _handle_anti_afk_challenge(self, data: Dict[str, Any]):
        """Menjawab tantangan anti-AFK dan mencatat latensi ke Supabase."""
        t0 = time.time()
        log.info("[%s] 🚨 Tantangan Anti-AFK terdeteksi! Mengklik 'Yes, keep farming'...", self.label)
        try:
            self.engine.handle_anti_afk(data)
            latency_ms = int((time.time() - t0) * 1000)
            log.info("[%s] ✅ Anti-AFK terjawab dalam %.2fs!", self.label, latency_ms / 1000.0)

            self.supabase.log_event(
                self.account_id,
                "ANTI_AFK_SOLVED",
                "INFO",
                f"Verifikasi anti-AFK berhasil dijawab (Latensi: {latency_ms/1000.0:.2f}s).",
                {"latency_ms": latency_ms},
            )
        except Exception as exc:
            err_msg = f"Gagal menyelesaikan verifikasi anti-AFK: {exc}"
            log.critical("[%s] %s", self.label, err_msg)
            self.supabase.log_event(self.account_id, "ANTI_AFK_FAILED", "CRITICAL", err_msg)
            self.notifier.send_alert(
                "[CRITICAL] Anti-AFK Verification Failed",
                f"Bot `{self.label}` gagal menjawab verifikasi anti-AFK! Mohon cek akun segera.",
                "CRITICAL",
                self.label,
            )

    def _read_gems_safe(self, data: Dict[str, Any]) -> Optional[int]:
        """Ekstraksi angka gems secara aman dengan fallback regex."""
        if hasattr(self.engine, "read_gems"):
            try:
                val = self.engine.read_gems([data])
                if val is not None:
                    return val
            except Exception:
                pass

        try:
            text = self.engine.message_text(data)
            rx = getattr(self.engine, "_rx_gem", None)
            if not rx:
                rx = re.compile(r"Gems\*{0,2}\s*[:=]\s+\*{0,2}([\d.,]+)\*{0,2}", re.I)
            wx = rx.search(text)
            if wx:
                digits = re.sub(r"\D", "", wx.group(1))
                return int(digits)
        except Exception:
            pass
        return None

    def _process_growcord_embed(self, data: Dict[str, Any]):
        """Membaca isi embed utama Growcord Farm."""
        try:
            text = self.engine.message_text(data)
        except Exception:
            return

        if "Growcord Farm" in text:
            # Baca Gems secara aman
            gems = self._read_gems_safe(data)
            if gems is not None:
                self.last_gems = gems
                if gems < self.gem_floor:
                    log.warning("[%s] ⚠️ Saldo gems (%d) di bawah gem_floor (%d)!", self.label, gems, self.gem_floor)
                    self.supabase.log_event(
                        self.account_id,
                        "LOW_GEMS_WARNING",
                        "WARNING",
                        f"Saldo gems ({gems:,}) berada di bawah batas Gem Floor ({self.gem_floor:,}).",
                    )

            # Baca Stock
            try:
                stock = self.engine.read_farmable_stock([data])
                if stock is not None:
                    self.last_stock = stock
                    if stock <= 0 and not self._paused:
                        now = time.time()
                        # Beri jeda minimal 60 detik antar percobaan restock agar tidak spamming toko jika inven sudah penuh
                        if now - getattr(self, "_last_restock_time", 0.0) >= 60.0:
                            self._last_restock_time = now
                            log.info("[%s] Stok farmable 0. Mencoba restock '%s'...", self.label, self.farmable_item)
                            try:
                                self.engine.buy_farmable(self.farmable_item)
                                self.engine.goto("home")
                                set_autofarm_state(self.engine, "ON")
                                self.supabase.log_event(
                                    self.account_id,
                                    "SHOP_PURCHASE",
                                    "INFO",
                                    f"Auto-restock farmable '{self.farmable_item}' diproses.",
                                )
                            except GemsExhaustedError:
                                self._handle_critical_error("Gems habis saat mencoba auto-restock di toko.")
                            except Exception as exc:
                                log.warning("[%s] Gagal restock farmable: %s", self.label, exc)
            except Exception as exc:
                log.debug("[%s] Error baca stok: %s", self.label, exc)

            # Baca Buff
            try:
                buffs = self.engine.read_active_buffs([data])
                if buffs:
                    self._update_buff_cache(buffs)
            except Exception as exc:
                log.debug("[%s] Error baca buff: %s", self.label, exc)

            # Persistensikan snapshot status ke file cache lokal (Atomic Write)
            if self.last_gems > 0:
                save_account_state(
                    account_id=self.account_id,
                    gems=self.last_gems,
                    stock=self.last_stock,
                    buff_clover=self.last_buff_clover,
                    buff_arroz=self.last_buff_arroz,
                    buff_benedict=self.last_buff_benedict,
                )

    def _update_buff_cache(self, buffs: Dict[str, str]):
        for name, dur_str in buffs.items():
            sec = parse_duration_to_sec(dur_str)
            low_name = name.lower()
            if "clover" in low_name:
                self.last_buff_clover = sec
            elif "arroz" in low_name:
                self.last_buff_arroz = sec
            elif "benedict" in low_name:
                self.last_buff_benedict = sec

    def _send_telemetry_update(self):
        """Kirim snapshot metrik ke Supabase."""
        try:
            ping_ms = getattr(self.gw, "latency_ms", 45) or 45
            is_farming = not self._paused and getattr(self.engine, "autofarm_state", "ON") == "ON"

            # Selalu perbarui heartbeat akun
            self.supabase.update_heartbeat(self.account_id, ping_ms)

            # Guard: Jangan kirim snapshot jika data embed belum pernah terbaca (gems & stock masih 0)
            if self.last_gems <= 0 and self.last_stock <= 0:
                log.debug("[%s] Melewati simpan metrics_history karena data belum siap (gems/stock masih 0).", self.label)
                return

            self.supabase.report_metrics(
                account_id=self.account_id,
                gems_balance=self.last_gems,
                stock_remaining=self.last_stock,
                is_farming=is_farming,
                buff_clover_sec=self.last_buff_clover,
                buff_arroz_sec=self.last_buff_arroz,
                buff_benedict_sec=self.last_buff_benedict,
                gateway_ping_ms=ping_ms,
            )
        except Exception as exc:
            log.debug("[%s] Telemetri update error: %s", self.label, exc)

    def _execute_remote_command(self, cmd_obj: Dict[str, Any]):
        """Menjalankan perintah remote dari dashboard."""
        command = cmd_obj.get("command")
        log.info("[%s] ⚡ Menjalankan remote command: %s", self.label, command)

        try:
            if command == "PAUSE":
                self._paused = True
                set_autofarm_state(self.engine, "OFF")
                self.supabase.update_account_status(self.account_id, "PAUSED")
                self.supabase.log_event(self.account_id, "SYSTEM", "WARNING", "Bot dijeda via dashboard.")

            elif command == "START":
                self._paused = False
                set_autofarm_state(self.engine, "ON")
                self.supabase.update_account_status(self.account_id, "ACTIVE")
                self.supabase.log_event(self.account_id, "SYSTEM", "INFO", "Bot dijalankan via dashboard.")

            elif command == "FORCE_REBUFF":
                log.info("[%s] Menjalankan Force Re-buff...", self.label)
                # Konsumsi buff
                try:
                    prepare_autofarm(self.engine)
                    self.supabase.log_event(self.account_id, "BUFF_APPLIED", "INFO", "Force Re-buff berhasil dieksekusi.")
                except Exception as exc:
                    log.warning("[%s] Force rebuff ada kendala: %s", self.label, exc)

            elif command == "FORCE_RESTOCK":
                log.info("[%s] Menjalankan Force Restock '%s'...", self.label, self.farmable_item)
                try:
                    self.engine.buy_farmable(self.farmable_item)
                    self.engine.goto("home")
                    self.supabase.log_event(
                        self.account_id,
                        "SHOP_PURCHASE",
                        "INFO",
                        f"Force Restock {self.farmable_item} berhasil.",
                    )
                except Exception as exc:
                    log.warning("[%s] Force restock gagal: %s", self.label, exc)

            elif command == "STOP":
                self._running = False

        except Exception as exc:
            log.error("[%s] Gagal mengeksekusi remote command %s: %s", self.label, command, exc)

    def _handle_critical_error(self, message: str):
        log.critical("[%s] [KRITIS] %s", self.label, message)
        self.supabase.update_account_status(self.account_id, "ERROR")
        self.supabase.log_event(self.account_id, "ERROR", "CRITICAL", message)
        self.notifier.send_alert(
            f"[CRITICAL] Bot Incident: {self.label}",
            f"Kendala kritis terdeteksi: `{message}`\nWorker bot dihentikan sementara.",
            "CRITICAL",
            self.label,
        )
