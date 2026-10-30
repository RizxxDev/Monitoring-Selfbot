from datetime import datetime, timezone
import json
import logging
import os
import requests
from typing import Any, Dict, List, Optional

log = logging.getLogger("growcord.supabase")

# Default credentials ke project Supabase aktif
DEFAULT_SUPABASE_URL = "https://kwogpweprnkpqquasshr.supabase.co"
DEFAULT_SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imt3b2dwd2Vwcm5rcHFxdWFzc2hyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTMzNjY2NTYsImV4cCI6MjEwODk0MjY1Nn0.oxiKZgrDdvi4NTz6NE9haX0jG4ohVixCmAupzdNQ3iE"
)


class SupabaseClient:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        self.url = (url or os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")

        # Jika belum ada di env, cari di berbagai lokasi file .env
        if not self.url or not self.key:
            self._load_from_all_env_files()

        # Coba juga dari worker/config.py jika ada
        if not self.url or not self.key:
            self._try_load_from_config()

        # Fallback terakhir ke default project yang sudah dibuat
        if not self.url:
            self.url = DEFAULT_SUPABASE_URL
        if not self.key:
            self.key = DEFAULT_SUPABASE_KEY

        self.rest_url = f"{self.url}/rest/v1"
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _load_from_all_env_files(self):
        worker_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(worker_dir)
        candidates = [
            os.path.join(worker_dir, ".env"),
            os.path.join(worker_dir, ".env.local"),
            os.path.join(root_dir, ".env"),
            os.path.join(root_dir, ".env.local"),
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.getcwd(), ".env.local"),
        ]

        for path in candidates:
            if os.path.isfile(path):
                self._parse_env_file(path)
                if self.url and self.key:
                    break

    def _parse_env_file(self, filepath: str):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        # Hapus tanda kutip jika ada
                        v = v.strip().strip("'\"")
                        if (k in ("NEXT_PUBLIC_SUPABASE_URL", "SUPABASE_URL")) and not self.url:
                            self.url = v.rstrip("/")
                            os.environ["NEXT_PUBLIC_SUPABASE_URL"] = self.url
                        elif (k in ("NEXT_PUBLIC_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY", "SUPABASE_KEY")) and not self.key:
                            self.key = v
                            os.environ["NEXT_PUBLIC_SUPABASE_ANON_KEY"] = self.key
        except Exception:
            pass

    def _try_load_from_config(self):
        try:
            import config as cfg
            if hasattr(cfg, "SUPABASE_URL") and getattr(cfg, "SUPABASE_URL"):
                self.url = getattr(cfg, "SUPABASE_URL").rstrip("/")
            if hasattr(cfg, "SUPABASE_KEY") and getattr(cfg, "SUPABASE_KEY"):
                self.key = getattr(cfg, "SUPABASE_KEY")
        except Exception:
            pass

    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    def get_accounts(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Mengambil daftar akun dari tabel accounts."""
        if not self.is_configured():
            return []
        endpoint = f"{self.rest_url}/accounts?select=*"
        if status:
            endpoint += f"&status=eq.{status}"
        try:
            res = requests.get(endpoint, headers=self.headers, timeout=10)
            if res.status_code == 200:
                return res.json()
            log.error("Gagal mengambil accounts [%d]: %s", res.status_code, res.text)
        except Exception as exc:
            log.error("Koneksi Supabase error saat get_accounts: %s", exc)
        return []

    def update_heartbeat(self, account_id: str, ping_ms: Optional[int] = None) -> bool:
        """Memperbarui last_heartbeat pada akun."""
        if not self.is_configured():
            return False
        now_iso = datetime.now(timezone.utc).isoformat()
        payload: Dict[str, Any] = {"last_heartbeat": now_iso}
        try:
            res = requests.patch(
                f"{self.rest_url}/accounts?id=eq.{account_id}",
                headers=self.headers,
                json=payload,
                timeout=8,
            )
            return res.status_code in (200, 204)
        except Exception as exc:
            log.debug("Heartbeat error %s: %s", account_id, exc)
            return False

    def update_account_status(self, account_id: str, status: str) -> bool:
        """Mengubah status operasional akun (ACTIVE, PAUSED, ERROR)."""
        if not self.is_configured():
            return False
        try:
            res = requests.patch(
                f"{self.rest_url}/accounts?id=eq.{account_id}",
                headers=self.headers,
                json={"status": status, "updated_at": datetime.now(timezone.utc).isoformat()},
                timeout=8,
            )
            return res.status_code in (200, 204)
        except Exception as exc:
            log.error("Gagal update status akun %s: %s", account_id, exc)
            return False

    def report_metrics(
        self,
        account_id: str,
        gems_balance: int = 0,
        stock_remaining: int = 0,
        is_farming: bool = True,
        buff_clover_sec: int = 0,
        buff_arroz_sec: int = 0,
        buff_benedict_sec: int = 0,
        gateway_ping_ms: int = 0,
    ) -> bool:
        """Menyimpan snapshot metrik telemetri ke tabel metrics_history."""
        if not self.is_configured():
            return False
        payload = {
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gems_balance": int(gems_balance),
            "stock_remaining": int(stock_remaining),
            "is_farming": bool(is_farming),
            "buff_clover_sec": int(buff_clover_sec),
            "buff_arroz_sec": int(buff_arroz_sec),
            "buff_benedict_sec": int(buff_benedict_sec),
            "gateway_ping_ms": int(gateway_ping_ms),
        }
        try:
            res = requests.post(f"{self.rest_url}/metrics_history", headers=self.headers, json=payload, timeout=8)
            return res.status_code in (200, 201)
        except Exception as exc:
            log.error("Gagal report metrics %s: %s", account_id, exc)
            return False

    def log_event(
        self,
        account_id: str,
        event_type: str,
        severity: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mencatat kejadian penting atau error ke tabel event_logs."""
        if not self.is_configured():
            return False
        payload = {
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "metadata": metadata or {},
        }
        try:
            res = requests.post(f"{self.rest_url}/event_logs", headers=self.headers, json=payload, timeout=8)
            return res.status_code in (200, 201)
        except Exception as exc:
            log.error("Gagal log event %s: %s", account_id, exc)
            return False

    def get_pending_commands(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Mengambil perintah remote berstatus PENDING dari tabel bot_commands."""
        if not self.is_configured():
            return []
        endpoint = f"{self.rest_url}/bot_commands?status=eq.PENDING&order=created_at.asc"
        if account_id:
            endpoint += f"&account_id=eq.{account_id}"
        try:
            res = requests.get(endpoint, headers=self.headers, timeout=8)
            if res.status_code == 200:
                return res.json()
        except Exception as exc:
            log.error("Gagal ambil pending commands: %s", exc)
        return []

    def set_command_status(self, command_id: int, status: str = "EXECUTED") -> bool:
        """Memperbarui status perintah remote (EXECUTED, FAILED)."""
        if not self.is_configured():
            return False
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            res = requests.patch(
                f"{self.rest_url}/bot_commands?id=eq.{command_id}",
                headers=self.headers,
                json={"status": status, "executed_at": now_iso},
                timeout=8,
            )
            return res.status_code in (200, 204)
        except Exception as exc:
            log.error("Gagal update command %d status: %s", command_id, exc)
            return False


if __name__ == "__main__":
    client = SupabaseClient()
    print("Supabase configured:", client.is_configured(), "URL:", client.url)
    accounts = client.get_accounts()
    print("Accounts count in DB:", len(accounts))
