import logging
import os
import signal
import sys
import time
from typing import Dict

# Pastikan folder worker selalu ada di sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot_worker import BotWorker
from crypto_utils import decrypt_token
from notifier import DiscordNotifier
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

    def start(self):
        """Memulai loop sinkronisasi multi-akun dan penanganan perintah remote."""
        if not self.supabase.is_configured():
            log.error("Supabase belum terkonfigurasi. Pastikan NEXT_PUBLIC_SUPABASE_URL dan KEY tersedia.")
            return

        self.running = True
        log.info("=" * 60)
        log.info(" MULTI-ACCOUNT DISCORD AUTOFARM WORKER ENGINE (SERVER A)")
        log.info(" Connected to Supabase: %s", self.supabase.url)
        log.info(" Discord Webhook Alert: %s", "Aktif" if self.notifier.is_configured() else "Nonaktif")
        log.info("=" * 60)

        last_acc_check = 0.0

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
        """Membaca tabel accounts dan menyinkronkan thread worker."""
        accounts = self.supabase.get_accounts()
        if not accounts:
            log.debug("Belum ada akun di tabel accounts atau database kosong.")
            return

        db_active_ids = set()

        for acc in accounts:
            acc_id = acc["id"]
            label = acc.get("label", "Unknown")
            status = acc.get("status", "ACTIVE")
            raw_token = acc.get("encrypted_token", "")
            channel_id = acc.get("channel_id", "")
            farmable_item = acc.get("farmable_item", "pot o' gems")
            gem_floor = acc.get("gem_floor", 2000)

            if status == "ACTIVE":
                db_active_ids.add(acc_id)
                # Jika belum berjalan atau thread sudah mati, nyalakan
                worker = self.workers.get(acc_id)
                if worker is None or not worker.is_alive():
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
                        self.supabase.update_account_status(acc_id, "ERROR")

            elif status in ("PAUSED", "OFFLINE"):
                # Jika status di DB diubah jadi PAUSED/OFFLINE tapi worker masih jalan, hentikan
                if acc_id in self.workers:
                    log.info("[manager] Akun '%s' berstatus %s, menghentikan worker...", label, status)
                    worker = self.workers.pop(acc_id)
                    worker.stop()

        # Bersihkan worker yang tidak lagi ada di tabel
        all_db_ids = {a["id"] for a in accounts}
        for running_id in list(self.workers.keys()):
            if running_id not in all_db_ids:
                log.info("[manager] Akun %s dihapus dari database, menghentikan worker...", running_id[:8])
                self.workers.pop(running_id).stop()

    def _process_pending_commands(self):
        """Mengecek antrean perintah remote di bot_commands."""
        commands = self.supabase.get_pending_commands()
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
                # Jika worker belum jalan, perbarui status akun & nyalakan
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
