"""
State Store: Manajemen persistensi cache lokal status bot per-akun.
Menjamin nilai saldo Gems, Stok, dan Buff tetap tersimpan aman di disk lokal (atomic write)
dan langsung dimuat saat worker startup tanpa pernah kembali ke 0.
"""

import hashlib
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

log = logging.getLogger("growcord.state")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def ensure_cache_dir() -> str:
    """Memastikan folder cache lokal ada."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    return CACHE_DIR


def get_state_file_path(account_id: str) -> str:
    """Mengembalikan path file cache state untuk account_id tertentu."""
    ensure_cache_dir()
    safe_id = "".join(c for c in str(account_id) if c.isalnum() or c in ("-", "_"))
    return os.path.join(CACHE_DIR, f"state_{safe_id}.json")


def calculate_decayed_buffs(
    buff_clover: int,
    buff_arroz: int,
    buff_benedict: int,
    updated_at_iso: Optional[str],
) -> Tuple[int, int, int]:
    """
    Menghitung sisa durasi buff berdasarkan selisih waktu downtime bot.
    Misal bot mati selama 30 detik, durasi buff otomatis berkurang 30 detik.
    """
    if not updated_at_iso:
        return buff_clover, buff_arroz, buff_benedict

    try:
        updated_dt = datetime.fromisoformat(updated_at_iso.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        elapsed_sec = int(max(0, (now_dt - updated_dt).total_seconds()))
    except Exception:
        elapsed_sec = 0

    c = max(0, int(buff_clover or 0) - elapsed_sec)
    a = max(0, int(buff_arroz or 0) - elapsed_sec)
    b = max(0, int(buff_benedict or 0) - elapsed_sec)
    return c, a, b


def load_account_state(
    account_id: str,
    fallback_fetcher: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Memuat state snapshot terakhir dari disk lokal.
    Jika file lokal tidak ada / korup, panggil fallback_fetcher (misal query Supabase).
    """
    file_path = get_state_file_path(account_id)
    state: Dict[str, Any] = {
        "account_id": account_id,
        "gems_balance": 0,
        "stock_remaining": 0,
        "buff_clover_sec": 0,
        "buff_arroz_sec": 0,
        "buff_benedict_sec": 0,
        "updated_at": None,
    }

    # 1. Coba baca dari file lokal
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("gems_balance", 0) > 0:
                    c, a, b = calculate_decayed_buffs(
                        data.get("buff_clover_sec", 0),
                        data.get("buff_arroz_sec", 0),
                        data.get("buff_benedict_sec", 0),
                        data.get("updated_at"),
                    )
                    state.update(
                        {
                            "gems_balance": int(data.get("gems_balance", 0)),
                            "stock_remaining": int(data.get("stock_remaining", 0)),
                            "buff_clover_sec": c,
                            "buff_arroz_sec": a,
                            "buff_benedict_sec": b,
                            "updated_at": data.get("updated_at"),
                        }
                    )
                    log.info(
                        "[%s] Berhasil memuat local cache state: Gems=%s, Stock=%s",
                        account_id,
                        f"{state['gems_balance']:,}",
                        state["stock_remaining"],
                    )
                    return state
        except Exception as exc:
            log.warning("[%s] Gagal membaca state cache file: %s", account_id, exc)

    # 2. Jika lokal belum ada, coba bootstrap dari Supabase jika ada fetcher
    if fallback_fetcher:
        try:
            remote_data = fallback_fetcher()
            if remote_data and isinstance(remote_data, dict):
                gems = int(remote_data.get("gems_balance", 0))
                if gems > 0:
                    c, a, b = calculate_decayed_buffs(
                        remote_data.get("buff_clover_sec", 0),
                        remote_data.get("buff_arroz_sec", 0),
                        remote_data.get("buff_benedict_sec", 0),
                        remote_data.get("timestamp"),
                    )
                    state.update(
                        {
                            "gems_balance": gems,
                            "stock_remaining": int(remote_data.get("stock_remaining", 0)),
                            "buff_clover_sec": c,
                            "buff_arroz_sec": a,
                            "buff_benedict_sec": b,
                            "updated_at": remote_data.get("timestamp"),
                        }
                    )
                    log.info(
                        "[%s] Auto-bootstrap state dari cloud: Gems=%s, Stock=%s",
                        account_id,
                        f"{state['gems_balance']:,}",
                        state["stock_remaining"],
                    )
                    # Simpan ke cache lokal agar startup berikutnya instan
                    save_account_state(
                        account_id=account_id,
                        gems=state["gems_balance"],
                        stock=state["stock_remaining"],
                        buff_clover=state["buff_clover_sec"],
                        buff_arroz=state["buff_arroz_sec"],
                        buff_benedict=state["buff_benedict_sec"],
                    )
                    return state
        except Exception as exc:
            log.debug("[%s] Bootstrap fallback error: %s", account_id, exc)

    return state


def save_account_state(
    account_id: str,
    gems: int,
    stock: int,
    buff_clover: int = 0,
    buff_arroz: int = 0,
    buff_benedict: int = 0,
) -> bool:
    """
    Menyimpan snapshot state terbaru ke file lokal secara aman (Atomic Write).
    Tidak akan menyimpan jika gems bernilai <= 0.
    """
    if int(gems or 0) <= 0:
        return False

    file_path = get_state_file_path(account_id)
    tmp_path = f"{file_path}.tmp"

    payload = {
        "account_id": account_id,
        "gems_balance": int(gems),
        "stock_remaining": int(stock),
        "buff_clover_sec": int(buff_clover),
        "buff_arroz_sec": int(buff_arroz),
        "buff_benedict_sec": int(buff_benedict),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, file_path)
        return True
    except Exception as exc:
        log.warning("[%s] Gagal menyimpan local cache state: %s", account_id, exc)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


# =====================================================================
# MANAJEMEN CACHE DATA AKUN LOKAL (OFFLINE RESILIENCE & SMART HOT-RELOAD)
# =====================================================================

ACCOUNTS_CACHE_FILE = os.path.join(CACHE_DIR, "accounts.json")


def compute_accounts_hash(accounts: List[Dict[str, Any]]) -> str:
    """Menghitung hash SHA-256 representasi akun untuk mendeteksi perubahan cepat."""
    if not accounts:
        return ""
    # Sortir akun berdasarkan ID agar konsisten
    sorted_accs = sorted(accounts, key=lambda a: str(a.get("id", "")))
    canonical = []
    for a in sorted_accs:
        canonical.append(
            {
                "id": str(a.get("id", "")),
                "label": str(a.get("label", "")),
                "encrypted_token": str(a.get("encrypted_token", "")),
                "channel_id": str(a.get("channel_id", "")),
                "farmable_item": str(a.get("farmable_item", "")),
                "gem_floor": int(a.get("gem_floor", 0) or 0),
                "status": str(a.get("status", "ACTIVE")),
            }
        )
    raw_str = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


def load_cached_accounts() -> List[Dict[str, Any]]:
    """Memuat daftar akun tersimpan dari disk lokal."""
    ensure_cache_dir()
    if not os.path.isfile(ACCOUNTS_CACHE_FILE):
        return []

    try:
        with open(ACCOUNTS_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "accounts" in data:
                return data["accounts"]
            elif isinstance(data, list):
                return data
    except Exception as exc:
        log.warning("Gagal membaca cache akun lokal: %s", exc)

    return []


def save_cached_accounts(accounts: List[Dict[str, Any]]) -> bool:
    """Menyimpan daftar konfigurasi akun ke disk lokal secara aman (Atomic Write)."""
    ensure_cache_dir()
    tmp_path = f"{ACCOUNTS_CACHE_FILE}.tmp"

    payload = {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "accounts_hash": compute_accounts_hash(accounts),
        "total_accounts": len(accounts),
        "accounts": accounts,
    }

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, ACCOUNTS_CACHE_FILE)
        log.info("Daftar akun lokal berhasil disimpan (%d akun).", len(accounts))
        return True
    except Exception as exc:
        log.warning("Gagal menyimpan cache akun lokal: %s", exc)
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False


def detect_account_diff(
    old_accounts: List[Dict[str, Any]],
    new_accounts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Menganalisis perbedaan konfigurasi antara cache lokal lama dan data baru.
    Mengklasifikasikan perubahan menjadi:
      - added: akun baru yang harus di-spawn
      - removed: akun yang dihapus dan harus dimatikan
      - hot_reload: perubahan parameter ringan (farmable_item, gem_floor, label) tanpa restart bot
      - critical_reload: perubahan kritis (token, channel, status) yang perlu restart tertib
    """
    old_map = {str(a["id"]): a for a in old_accounts if "id" in a}
    new_map = {str(a["id"]): a for a in new_accounts if "id" in a}

    added: List[Dict[str, Any]] = []
    removed: List[str] = []
    hot_reload: List[Dict[str, Any]] = []
    critical_reload: List[Dict[str, Any]] = []

    # Cek akun baru & akun yang dimodifikasi
    for acc_id, new_acc in new_map.items():
        if acc_id not in old_map:
            added.append(new_acc)
        else:
            old_acc = old_map[acc_id]

            # 1. Cek parameter kritis
            token_changed = new_acc.get("encrypted_token") != old_acc.get("encrypted_token")
            channel_changed = str(new_acc.get("channel_id") or "") != str(old_acc.get("channel_id") or "")
            status_changed = new_acc.get("status") != old_acc.get("status")

            if token_changed or channel_changed or status_changed:
                critical_reload.append(new_acc)
            else:
                # 2. Cek parameter ringan yang bisa di-hot-reload
                item_changed = new_acc.get("farmable_item") != old_acc.get("farmable_item")
                floor_changed = int(new_acc.get("gem_floor", 0) or 0) != int(old_acc.get("gem_floor", 0) or 0)
                label_changed = new_acc.get("label") != old_acc.get("label")

                if item_changed or floor_changed or label_changed:
                    hot_reload.append(new_acc)

    # Cek akun yang dihapus
    for acc_id in old_map.keys():
        if acc_id not in new_map:
            removed.append(acc_id)

    has_changes = bool(added or removed or hot_reload or critical_reload)

    return {
        "has_changes": has_changes,
        "added": added,
        "removed": removed,
        "hot_reload": hot_reload,
        "critical_reload": critical_reload,
    }

