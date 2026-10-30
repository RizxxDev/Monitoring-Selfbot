"""
State Store: Manajemen persistensi cache lokal status bot per-akun.
Menjamin nilai saldo Gems, Stok, dan Buff tetap tersimpan aman di disk lokal (atomic write)
dan langsung dimuat saat worker startup tanpa pernah kembali ke 0.
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

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
