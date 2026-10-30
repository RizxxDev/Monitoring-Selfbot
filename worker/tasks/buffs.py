import logging
import re
import time

import config as cfg
from core.api import ApiError, GemsExhaustedError
from core.bot import NavError

log = logging.getLogger("growcord.task")

ITEMS = [
    {"slug": "clover", "nama": "Lucky Clover", "beli": None},
    {"slug": "arroz", "nama": "Arroz Con Pollo", "beli": "beli_arroz"},
    {"slug": "eggs_benedict", "nama": "Eggs Benedict", "beli": "beli_benedict"},
]

RX_ALREADY = re.compile(r"timer\s*was\s*not\s*refreshed|sudah\s*aktif", re.IGNORECASE)


def _sudah_aktif(engine, nama, aktif):
    for k, sisa in aktif.items():
        if k.lower() == nama.lower():
            return sisa
    return None


def _have_item(engine, nama):
    screen, doc = engine.goto("consumables")
    sel = engine._match_button(doc, screen.pattern("select_item"))
    if sel is None:
        log.info("[buff] select tidak ada (inventory kosong) -> perlu beli")
        return False
    options = engine._select_options(doc, sel["custom_id"])
    pat = re.compile(re.escape(nama), re.IGNORECASE)
    return any(pat.search(o.get("label") or "") for o in options)


def _use_once(engine, nama, aktif):
    """Kembali ke Consumables, pilih item di select menu, klik Use."""
    sisa = _sudah_aktif(engine, nama, aktif)
    if sisa is not None:
        log.info(
            "[buff] %s masih aktif (%s) -> tidak di-reuse",
            nama,
            engine.fmt_durasi(sisa),
        )
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
    except (NavError, ApiError) as exc:
        log.warning("[buff] Gagal memilih '%s' di select: %s", nama, exc)
        return False

    if not engine.wait_selected(nama):
        log.warning("[buff] Timeout konfirmasi terpilihnya '%s'", nama)
        return False

    try:
        engine.click_screen_button("consumables", "use")
    except (NavError, ApiError) as exc:
        log.warning("[buff] Gagal menekan tombol 'Use' untuk '%s': %s", nama, exc)
        return False

    modal = engine.capture_modal(1.5)
    if modal:
        try:
            engine._submit_spawned(modal, 1)
        except Exception as exc:
            log.warning("[buff] Gagal submit modal form use '%s': %s", nama, exc)

    reply = engine.wait_bot_reply(cfg.REPLY_TIMEOUT)
    if reply is None:
        log.warning("[buff] balasan use %s tidak terdeteksi", nama)
        return False
    text = engine.message_text(reply)
    if RX_ALREADY.search(text):
        log.info("[buff] %s: sudah aktif (stok terpakai tanpa refresh timer)", nama)
        return True
    reason = engine.abort_reason(text)
    if reason:
        log.warning("[buff] use %s ditolak bot: %s", nama, reason)
        return False
    return True


def run(engine, args):
    bought = 0
    engine.goto("home")
    aktif = engine.read_active_buffs()
    for item in ITEMS:
        nama, beli = item["nama"], item["beli"]
        # Jika Lucky Clover dan sudah pernah dicek di awal tanpa sisa stok, lewati jika tidak aktif
        if beli is None and (getattr(engine, "clover_checked", False) is True) and (getattr(engine, "clover_has_more", False) is not True):
            if not _sudah_aktif(engine, nama, aktif):
                log.info(
                    "[buff] %s tidak aktif dan tidak dijual di Toko, lewati...",
                    nama,
                )
                continue

        log.info("[buff] memproses %s", nama)
        sisa = _sudah_aktif(engine, nama, aktif)
        if sisa is not None:
            log.info(
                "[buff] %s masih aktif (%s), lewati",
                nama,
                engine.fmt_durasi(sisa),
            )
            continue
        if not _have_item(engine, nama):
            log.info("[buff] %s belum dimiliki", nama)
            if beli is None:
                log.warning("[buff] %s tidak ada di inventory, lewati", nama)
                engine.clover_checked = True
                engine.clover_has_more = False
                continue
            log.info("[buff] %s tidak tersedia -> beli x5 di Toko Consumables", nama)
            bought_ok = False
            for buy_attempt in range(1, 3):
                try:
                    engine.goto("shop_consumable")
                    engine.buy_with_form("shop_consumable", beli, 5)
                    reply = engine.wait_bot_reply(cfg.REPLY_TIMEOUT)
                    if reply is not None:
                        reason = engine.abort_reason(engine.message_text(reply))
                        if reason:
                            low = reason.lower()
                            if any(w in low for w in ("tidak cukup", "insufficient", "kehabisan", "gems")):
                                raise GemsExhaustedError(f"Pembelian buff {nama} ditolak (Gems habis): {reason}")
                            log.warning("[buff] beli %s ditolak: %s", nama, reason)
                            break
                    bought_ok = True
                    bought += 1
                    break
                except (NavError, ApiError) as exc:
                    log.warning("[buff] Kendala saat beli %s (percobaan %d): %s", nama, buy_attempt, exc)
                    time.sleep(2.0)

            if not bought_ok:
                log.warning("[buff] Gagal membeli %s di Toko Consumables, lewati...", nama)
                continue

        used = False
        for attempt in (1, 2):
            try:
                if _use_once(engine, nama, engine.read_active_buffs()):
                    used = True
                    log.info("[buff] %s: digunakan%s", nama, " (setelah beli)" if bought else "")
                    break
            except (NavError, ApiError) as exc:
                log.warning("[buff] Kendala saat use %s (percobaan %d): %s", nama, attempt, exc)
            log.warning("[buff] use %s percobaan %d gagal, ulangi", nama, attempt)
            time.sleep(2.0)
        if not used:
            log.warning("[buff] Tidak dapat mengaktifkan %s pada siklus ini", nama)
    engine.goto("home")
    log.info("[buff] selesai, %s jenis item dibeli", bought)
