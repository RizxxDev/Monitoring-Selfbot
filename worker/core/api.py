import json
import logging
import random
import time

import requests

BASE = "https://discord.com/api/v10"

log = logging.getLogger("growcord.api")


class ApiError(Exception):
    pass


class AuthError(ApiError):
    pass


class GemsExhaustedError(ApiError):
    pass


def nonce():
    return str(
        ((int(time.time() * 1000) - 1420070400000) << 22) + random.randint(0, 4194304)
    )


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
        url = BASE + path
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
                    "Ambil token baru dan perbarui config.py."
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
        raise ApiError(f"{method} {path} gagal setelah {retries} percobaan ({last_error})")

    def channel_info(self, channel_id):
        return self.request("GET", f"/channels/{channel_id}")

    def get_guilds(self):
        docs = self.request("GET", "/users/@me/guilds?limit=200")
        return docs or []

    def guild_channels(self, guild_id):
        try:
            data = self.request("GET", f"/guilds/{guild_id}/channels")
        except ApiError as exc:
            log.info("skip guild %s: %s", guild_id, exc)
            return []
        return data or []

    def get_messages(self, channel_id, limit=25):
        data = self.request(
            "GET", f"/channels/{channel_id}/messages?limit={limit}"
        )
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
                "data": {"custom_id": custom_id, "component_type": 3, "values": values},
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
