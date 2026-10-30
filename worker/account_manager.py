import logging
import os
import signal
import sys
import time
from typing import Any, Dict, List, Optional

# Pastikan folder worker selalu ada di sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_worker import BotWorker
from crypto_utils import decrypt_token
from notifier import DiscordNotifier
from state_store import (
    load_cached_accounts,
    save_cached_accounts,
    compute_accounts_hash,
    detect_account_diff,
)
from supabase_client import SupabaseClient

log = logging.getLogger("growcord.manager")


class AccountManager:
    def __init__(self, check_interval: float = 8.0, command_interval: float = 2.5):
        self.supabase = SupabaseClient()
        self.notifier = DiscordNotifier()
        self.check_interval = check_interval
        self.command_interval = command_interval

        self.workers: Dict[str, BotWorker] = {}
        self.running = False

        # Cache akun lokal (Offline resilience & smart change detection)
        self.cached_accounts: List[Dict[str, Any]] = load_cached_accounts()
        self.accounts_hash: str = compute_accounts_hash(self.cached_accounts)
        if self.cached_accounts:
            log.info("[manager] Memuat %d akun dari cache lokal (accounts.json).", len(self.cached_accounts))

    def _start_worker(self, acc: Dict[str, Any]):
        """Menjalankan worker bot baru untuk satu akun."""
        acc_id = acc["id"]
        label = acc.get("label", "Unknown")
        raw_token = acc.get("encrypted_token", "")
        channel_id = acc.get("channel_id", "")
        farmable_item = acc.get("farmable_item", "pot o' gems")
        gem_floor = acc.get("gem_floor", 2000)

        # Jika worker sudah ada dan masih berjalan, jangan buat dobel
        if acc_id in self.workers and self.workers[acc_id].is_alive():
            return

        log.info("[manager] Memulai worker baru untuk akun '%s' (%s)...", label, acc_id[:8])
        try:
            token = decrypt_token(raw_token)
            new_worker = BotWorker(
                account_id=acc_id,
                label=label,
                token=token,
                channel_id=channel_id,
                farmable_item=farmable_item,
                gem_floor=gem_floor,
                supabase=self.supabase,
                notifier=self.notifier,
            )
            new_worker.start()
            self.workers[acc_id] = new_worker
        except Exception as exc:
            log.error("[manager] Gagal memulai worker '%s': %s", label, exc)
            if self.supabase.is_configured():
                try:
                    self.supabase.update_account_status(acc_id, "ERROR")
                except Exception:
                    pass

    def _stop_worker(self, acc_id: str, label: str = ""):
        """Menghentikan worker bot secara aman."""
        worker = self.workers.pop(acc_id, None)
        if worker:
            log.info("[manager] Menghentikan worker akun '%s' (%s)...", label or acc_id[:8], acc_id[:8])
            try:
                worker.stop()
            except Exception:
                pass

    def start(self):
        """Memulai loop sinkronisasi multi-akun dan penanganan perintah remote."""
        self.running = True
        log.info("=" * 60)
        log.info(" MULTI-ACCOUNT DISCORD AUTOFARM WORKER ENGINE (SERVER A)")
        log.info(" Connected to Supabase: %s", getattr(self.supabase, "url", "Offline"))
        log.info(" Discord Webhook Alert: %s", "Aktif" if self.notifier.is_configured() else "Nonaktif")
        log.info(
            " Local Accounts Cache: %s (%d akun tersimpan)",
            "Tersedia" if self.cached_accounts else "Kosong",
            len(self.cached_accounts),
        )
        log.info("=" * 60)

        # Lakukan sinkronisasi awal akun saat booting
        self._sync_accounts()
        last_acc_check = time.time()

        try:
            while self.running:
                now = time.time()

                # 1. Cek & Jalankan Perintah Remote (Setiap 2-3 detik)
                self._process_pending_commands()

                # 2. Sinkronkan Daftar Akun dari Database Supabase (Setiap 8-10 detik)
                if now - last_acc_check >= self.check_interval:
                    self._sync_accounts()
                    last_acc_check = now

                time.sleep(self.command_interval)

        except KeyboardInterrupt:
            log.info("Sinyal Ctrl+C diterima. Menghentikan seluruh worker bot...")
        finally:
            self.stop_all()

    def _sync_accounts(self):
        """Membaca tabel accounts dari Supabase, membandingkan diff, dan memperbarui cache lokal."""
        remote_accounts: Optional[List[Dict[str, Any]]] = None
        if self.supabase.is_configured():
            try:
                remote_accounts = self.supabase.get_accounts()
            except Exception as exc:
                log.warning("[manager] Gagal menghubungi Supabase: %s. Beralih ke cache lokal...", exc)

        # Skenario 1: Supabase aktif dan mengembalikan respons
        if remote_accounts is not None:
            diff = detect_account_diff(self.cached_accounts, remote_accounts)

            if diff["has_changes"] or not self.cached_accounts:
                log.info(
                    "[manager] Perubahan konfigurasi akun terdeteksi: +%d baru, -%d dihapus, ~%d hot-reload, ⚡%d kritis.",
                    len(diff["added"]),
                    len(diff["removed"]),
                    len(diff["hot_reload"]),
                    len(diff["critical_reload"]),
                )

                # A. Hot-reload parameter ringan tanpa putus sesi Discord
                for acc in diff["hot_reload"]:
                    acc_id = acc["id"]
                    worker = self.workers.get(acc_id)
                    if worker and worker.is_alive():
                        worker.update_config(
                            farmable_item=acc.get("farmable_item"),
                            gem_floor=acc.get("gem_floor"),
                            label=acc.get("label"),
                        )

                # B. Perubahan kritis (token baru, pindah channel, atau perubahan status)
                for acc in diff["critical_reload"]:
                    acc_id = acc["id"]
                    self._stop_worker(acc_id, acc.get("label", ""))
                    if acc.get("status") == "ACTIVE":
                        self._start_worker(acc)

                # C. Akun baru ditambahkan lewat dashboard
                for acc in diff["added"]:
                    if acc.get("status") == "ACTIVE":
                        self._start_worker(acc)

                # D. Akun dihapus dari dashboard
                for acc_id in diff["removed"]:
                    self._stop_worker(acc_id)

                # Perbarui file cache lokal di disk secara aman (Atomic Write)
                save_cached_accounts(remote_accounts)
                self.cached_accounts = remote_accounts
                self.accounts_hash = compute_accounts_hash(remote_accounts)

            else:
                # Tidak ada perubahan diff; pastikan akun berstatus ACTIVE yang mati otomatis di-restart
                for acc in remote_accounts:
                    acc_id = acc["id"]
                    if acc.get("status") == "ACTIVE":
                        worker = self.workers.get(acc_id)
                        if worker is None or not worker.is_alive():
                            self._start_worker(acc)
                    elif acc.get("status") in ("PAUSED", "OFFLINE"):
                        if acc_id in self.workers:
                            self._stop_worker(acc_id, acc.get("label", ""))

        # Skenario 2: Offline Fallback (Internet atau Supabase down)
        else:
            if self.cached_accounts:
                log.info("[manager] [OFFLINE MODE] Menjalankan bot dari cache lokal (%d akun)...", len(self.cached_accounts))
                for acc in self.cached_accounts:
                    if acc.get("status") == "ACTIVE":
                        acc_id = acc["id"]
                        worker = self.workers.get(acc_id)
                        if worker is None or not worker.is_alive():
                            self._start_worker(acc)

    def _process_pending_commands(self):
        """Mengecek antrean perintah remote di bot_commands."""
        if not self.supabase.is_configured():
            return

        try:
            commands = self.supabase.get_pending_commands()
        except Exception:
            return

        if not commands:
            return

        for cmd in commands:
            cmd_id = cmd["id"]
            acc_id = cmd["account_id"]
            command = cmd["command"]
            payload = cmd.get("payload") or {}

            log.info("[manager] Menerima remote command #%d: %s untuk akun %s", cmd_id, command, acc_id[:8])

            worker = self.workers.get(acc_id)

            if command == "START":
                self.supabase.update_account_status(acc_id, "ACTIVE")
                self.supabase.set_command_status(cmd_id, "EXECUTED")
                self._sync_accounts()
                continue

            if worker and worker.is_alive():
                worker.queue_command({"command": command, "payload": payload})
                self.supabase.set_command_status(cmd_id, "EXECUTED")
            else:
                log.warning("[manager] Worker akun %s tidak aktif, perintah %s ditolak.", acc_id[:8], command)
                self.supabase.set_command_status(cmd_id, "FAILED")

    def stop_all(self):
        """Menghentikan seluruh worker bot."""
        log.info("[manager] Menghentikan %d worker bot yang aktif...", len(self.workers))
        for acc_id, worker in list(self.workers.items()):
            try:
                worker.stop()
            except Exception:
                pass
        self.workers.clear()
        log.info("[manager] Seluruh worker telah dimatikan.")


def main():
    # Setup logging ke console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    manager = AccountManager()

    def handle_sigterm(signum, frame):
        log.info("Menerima sinyal termination.")
        manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)

    manager.start()


if __name__ == "__main__":
    main()
