from datetime import datetime, timezone
import json
import logging
import os
import requests
from typing import Any, Dict, Optional

log = logging.getLogger("growcord.notifier")

# Warna embed Discord (decimal)
COLOR_CRITICAL = 0xFF3333  # Merah
COLOR_WARNING = 0xFFAA00   # Kuning / Oranye
COLOR_INFO = 0x00CC66      # Hijau


class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_ALERT_WEBHOOK_URL", "")
        if not self.webhook_url:
            self._try_load_env()

    def _try_load_env(self):
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.local")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DISCORD_ALERT_WEBHOOK_URL="):
                        self.webhook_url = line.split("=", 1)[1].strip()

    def is_configured(self) -> bool:
        return bool(self.webhook_url and self.webhook_url.startswith("https://discord.com/api/webhooks/"))

    def send_alert(
        self,
        title: str,
        description: str,
        severity: str = "INFO",
        account_label: str = "System",
        fields: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mengirim pesan embed peringatan ke channel Discord pribadi."""
        if not self.is_configured():
            log.debug("Discord webhook belum dikonfigurasi, skip kirim alert: %s", title)
            return False

        color = COLOR_INFO
        if severity == "CRITICAL":
            color = COLOR_CRITICAL
        elif severity == "WARNING":
            color = COLOR_WARNING

        embed_fields = [
            {"name": "Akun", "value": f"`{account_label}`", "inline": True},
            {"name": "Severity", "value": f"`{severity}`", "inline": True},
            {
                "name": "Waktu",
                "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": False,
            },
        ]

        if fields:
            for k, v in fields.items():
                embed_fields.append({"name": str(k), "value": f"`{v}`", "inline": True})

        payload = {
            "username": "Growcord Monitor Sentinel",
            "avatar_url": "https://cdn.discordapp.com/embed/avatars/0.png",
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": color,
                    "fields": embed_fields,
                    "footer": {
                        "text": "Multi-Account Autofarm Watchdog Engine",
                    },
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }

        try:
            res = requests.post(self.webhook_url, json=payload, timeout=8)
            if res.status_code in (200, 204):
                log.info("Peringatan terkirim ke Discord Webhook: %s", title)
                return True
            log.error("Gagal kirim webhook Discord [%d]: %s", res.status_code, res.text)
        except Exception as exc:
            log.error("Error koneksi webhook Discord: %s", exc)

        return False


if __name__ == "__main__":
    notifier = DiscordNotifier()
    print("Discord Webhook configured:", notifier.is_configured())
