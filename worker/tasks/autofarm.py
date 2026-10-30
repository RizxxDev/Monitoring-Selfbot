import logging
import time

import config as cfg
from core.api import ApiError, AuthError, GemsExhaustedError
from core.bot import NavError
from tasks import buffs

log = logging.getLogger("growcord.task")


def _set_autofarm_state(engine, desired):
    """Mengatur status Auto Farm di main menu menjadi ON atau OFF."""
    try:
        screen, msg = engine.goto("home")
    except NavError as exc:
        log.warning("Gagal navigasi ke home saat set autofarm: %s", exc)
        return False
    current = engine.read_autofarm_state([msg] if msg else None)
    if current is None:
        current = engine.read_autofarm_state()
    if current is None:
        log.warning(
            "status 'Auto Farm:' tidak ditemukan pada embed. Menunda ke siklus berikutnya."
        )
        return False

    log.info("status auto farm: %s -> target %s", current, desired)
    if current == desired:
        log.info("auto farm sudah %s, tidak ada aksi", desired)
        return True

    for attempt in range(1, 6):
        try:
            screen, msg = engine.goto("home")
        except NavError:
            pass
        current = engine.read_autofarm_state([msg] if msg else None)
        if current == desired:
            log.info("auto farm sekarang: %s", desired)
            return True
        try:
            engine.click_screen_button("home", "farm", msg=msg)
        except (NavError, ApiError) as exc:
            if "disabled" in str(exc).lower():
                log.warning(
                    "percobaan %d: tombol Farm disabled (cooldown server), tunggu 3.5s...",
                    attempt,
                )
                time.sleep(3.5)
                continue
            log.warning("percobaan %d: gagal klik tombol Farm: %s", attempt, exc)
            time.sleep(2.0)
            continue
        time.sleep(1.5)
        _, fresh_msg = engine.locate()
        new_state = engine.read_autofarm_state([fresh_msg] if fresh_msg else None)
        if new_state == desired:
            log.info("auto farm sekarang: %s", desired)
            return True
        log.warning(
            "percobaan %d: status belum %s (terdeteksi: %s), tunggu...",
            attempt,
            desired,
            new_state,
        )
        time.sleep(2.0)
    log.warning("auto farm belum berubah ke %s setelah 5 percobaan, akan dicoba kembali nanti", desired)
    return False


def _has_buff(aktif_dict, buff_name):
    if not aktif_dict:
        return False
    target = buff_name.lower()
    for k, sisa in aktif_dict.items():
        if target in k.lower():
            if isinstance(sisa, (int, float)):
                return sisa > 0
            return True
    return False


def _prepare_autofarm(engine):
    """Alur persiapan lengkap autofarm:
    1. Cek stock farmable di main menu. Jika kosong (<= 0), beli Pot o' Gems di Toko -> Farmable -> Buy Max.
    2. Cek Lucky Clover sekali di awal (jika tidak ada di inventory, lewati).
    3. Cek buff Arroz Con Pollo & Eggs Benedict:
       - Jika buff aktif dan stok farmable > 0 -> langsung klik Farm jika OFF (tanpa buka menu lain).
       - Jika buff habis -> gunakan/beli -> Home.
    4. Pastikan Auto Farm ON di main menu.
    """
    log.info("========== PERSIAPAN AUTOFARM ==========")
    screen, msg = engine.goto("home")

    # 1. Cek Lucky Clover 1x di awal atau saat punya stok tersisa
    if not getattr(engine, "clover_checked", False) or getattr(engine, "clover_has_more", False):
        aktif_init = engine.read_active_buffs(msg)
        if not _has_buff(aktif_init, "Lucky Clover"):
            log.info("[autofarm] Memeriksa stok Lucky Clover di inventory...")
            from tasks.buffs import _have_item, _use_once
            if _have_item(engine, "Lucky Clover"):
                _use_once(engine, "Lucky Clover", aktif_init)
            else:
                log.info("[autofarm] Lucky Clover tidak ada di inventory, dilewati.")
                engine.clover_has_more = False
            screen, msg = engine.goto("home")
        engine.clover_checked = True

    # 2. Cek stock farmable & buff saat ini di main menu
    stock = engine.read_farmable_stock(msg)
    aktif = engine.read_active_buffs(msg)
    state = engine.read_autofarm_state([msg])

    if stock is not None:
        log.info("[autofarm] Stock farmable saat ini: %s block", engine.fmt_int(stock))
    else:
        log.warning("[autofarm] Status stock farmable tidak terbaca spesifik dari embed home")

    arroz_ok = _has_buff(aktif, "Arroz Con Pollo")
    benedict_ok = _has_buff(aktif, "Eggs Benedict")
    buffs_ok = arroz_ok and benedict_ok
    stock_ok = (stock is None or stock > 0)

    log.info(
        "[autofarm] Status: Stock OK=%s | Buffs Aktif=%s (Arroz=%s, Benedict=%s) | Auto Farm=%s",
        stock_ok,
        buffs_ok,
        arroz_ok,
        benedict_ok,
        state,
    )

    # Kondisi langsung klik Farm jika buff & stok sudah ada
    if stock_ok and buffs_ok:
        log.info("[autofarm] ✅ Buff sudah aktif dan stok farmable belum 0! Cukup pastikan Auto Farm: ON.")
        if state != "ON":
            log.info("[autofarm] Menyalakan Auto Farm (OFF -> ON)...")
            _set_autofarm_state(engine, "ON")
        else:
            log.info("[autofarm] Auto Farm sudah aktif (ON).")
        log.info("=========================================")
        return

    # Jika stok habis
    if stock is not None and stock <= 0:
        farmable_item = getattr(cfg, "FARMABLE_ITEM", "pot o' gems")
        log.warning(
            "[autofarm] Stock farmable kosong (%s)! Menuju Toko -> Farmable -> '%s' (Buy Max)...",
            stock,
            farmable_item,
        )
        engine.buy_farmable(farmable_item)
        screen, msg = engine.goto("home")
        stock = engine.read_farmable_stock(msg)
        log.info("[autofarm] Stock farmable setelah beli: %s", stock)

    # Jika buff habis / belum aktif
    if not buffs_ok:
        log.info("[autofarm] Memeriksa efek buff (Arroz, Eggs Benedict)...")
        buffs.run(engine, {})
        screen, msg = engine.goto("home")

    # Pastikan Auto Farm ON
    state = engine.read_autofarm_state([msg])
    log.info("[autofarm] Status Auto Farm di main menu: %s", state)
    if state != "ON":
        log.info("[autofarm] Menyalakan Auto Farm (OFF -> ON)...")
        _set_autofarm_state(engine, "ON")
    else:
        log.info("[autofarm] Auto Farm sudah aktif (ON).")
    log.info("=========================================")


def _full_autofarm_loop(engine, args):
    """Menjalankan persiapan awal lalu masuk ke mode standby (anti-AFK realtime listener)."""
    log.info("Memulai Sistem Auto Farm Terpadu...")

    # Cek apakah ada prompt anti-AFK lama yang belum terjawab
    engine.check_recent_anti_afk()

    # Jalankan persiapan lengkap
    _prepare_autofarm(engine)

    # Kuras antrean event Gateway secara aman tanpa menghilangkan Anti-AFK
    if hasattr(engine, "safe_drain_events"):
        engine.safe_drain_events()
    else:
        while engine.gw.pop_event(timeout=0) is not None:
            pass

    log.info("[autofarm] ✅ Semua persiapan siap! Masuk mode idle monitoring.")
    log.info("[autofarm] 📡 Memantau pesan bot secara realtime:")
    log.info("  - Anti-AFK: auto-respond 'are you still there?' -> 'Yes, keep farming'")
    log.info("  - Auto-Restock: jika farmable habis (0) -> otomatis beli Pot O' Gems")
    log.info("  - Auto-Rebuff: jika buff habis -> otomatis re-buff")
    log.info("Tekan Ctrl+C untuk menghentikan.")

    check_interval = int(getattr(cfg, "AUTOFARM_CHECK_INTERVAL", 300))  # default 5 menit
    last_check = time.time()

    try:
        while True:
            # Jika gateway mengalami error fatal (token revoked/invalid), hentikan loop
            if getattr(engine.gw, "fatal", False) is True:
                raise AuthError("Gateway fatal: token ditolak atau sesi tidak valid.")

            # Pastikan gateway siap
            if hasattr(engine.gw, "ready") and not engine.gw.ready.is_set():
                time.sleep(1.0)
                continue

            # Pop event dari gateway realtime
            event = engine.gw.pop_event(timeout=1.0)
            if event is not None:
                kind, data, _ts = event
                if kind in ("message_new", "message_edit"):
                    # Verifikasi pesan berasal dari target channel bot
                    msg_chan = str(data.get("channel_id") or "")
                    if engine.channel_id and msg_chan and msg_chan != str(engine.channel_id):
                        continue

                    # 1. Tangani tantangan anti-AFK bot
                    if engine.is_anti_afk_prompt(data):
                        engine.handle_anti_afk(data)
                        if hasattr(engine, "safe_drain_events"):
                            engine.safe_drain_events()
                        else:
                            while engine.gw.pop_event(timeout=0) is not None:
                                pass
                        continue

                    # 2. Deteksi pembaruan panel utama
                    if engine._is_growcord(data, cfg.GROWCORD_APP_ID):
                        text = engine.message_text(data)
                        if "Growcord Farm" in text:
                            stock = engine.read_farmable_stock([data])
                            aktif = engine.read_active_buffs([data])
                            current_state = engine.read_autofarm_state([data])

                            arroz_ok = _has_buff(aktif, "Arroz Con Pollo")
                            benedict_ok = _has_buff(aktif, "Eggs Benedict")

                            # Kasus A: Stok habis
                            if stock is not None and stock <= 0:
                                farmable_item = getattr(cfg, "FARMABLE_ITEM", "pot o' gems")
                                log.warning(
                                    "[autofarm] Terdeteksi stock farmable HABIS (%s)! Membeli '%s' (Buy Max)...",
                                    stock,
                                    farmable_item,
                                )
                                try:
                                    engine.buy_farmable(farmable_item)
                                    screen, msg = engine.goto("home")
                                    if engine.read_autofarm_state([msg]) != "ON":
                                        _set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat restock farmable: %s", exc)
                                    try:
                                        engine.goto("home")
                                    except Exception:
                                        pass
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                last_check = time.time()
                                continue

                            # Kasus B: Buff habis
                            has_buff_header = ("Buff Aktif" in text) or ("Aktif Buff" in text)
                            if has_buff_header and (not arroz_ok or not benedict_ok):
                                log.warning(
                                    "[autofarm] Buff terdeteksi habis (Arroz: %s, Benedict: %s)! Menjalankan re-buff...",
                                    arroz_ok,
                                    benedict_ok,
                                )
                                try:
                                    buffs.run(engine, {})
                                    screen, msg = engine.goto("home")
                                    if engine.read_autofarm_state([msg]) != "ON":
                                        _set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat re-buff: %s", exc)
                                    try:
                                        engine.goto("home")
                                    except Exception:
                                        pass
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                last_check = time.time()
                                continue

                            # Kasus C: Auto Farm OFF padahal stok & buff masih aktif
                            if current_state == "OFF" and (stock is None or stock > 0) and arroz_ok and benedict_ok:
                                log.info(
                                    "[autofarm] Auto Farm berstatus OFF tapi stok & buff masih aktif. Menyalakan kembali (klik Farm)..."
                                )
                                try:
                                    _set_autofarm_state(engine, "ON")
                                except Exception as exc:
                                    log.warning("[autofarm] Kendala saat menyalakan Auto Farm: %s", exc)
                                if hasattr(engine, "safe_drain_events"):
                                    engine.safe_drain_events()
                                else:
                                    while engine.gw.pop_event(timeout=0) is not None:
                                        pass
                                continue

            # Pengecekan berkala (heartbeat)
            if time.time() - last_check >= check_interval:
                last_check = time.time()
                log.info("[autofarm] Pemeriksaan berkala (interval %ds)...", check_interval)
                try:
                    screen, msg = engine.goto("home")
                    stock = engine.read_farmable_stock(msg)
                    aktif = engine.read_active_buffs(msg)
                    current_state = engine.read_autofarm_state([msg])

                    arroz_ok = _has_buff(aktif, "Arroz Con Pollo")
                    benedict_ok = _has_buff(aktif, "Eggs Benedict")

                    log.info(
                        "[autofarm] Heartbeat status: Stock=%s | Arroz=%s | Benedict=%s | Auto Farm=%s",
                        stock,
                        arroz_ok,
                        benedict_ok,
                        current_state,
                    )

                    if stock is not None and stock <= 0:
                        farmable_item = getattr(cfg, "FARMABLE_ITEM", "pot o' gems")
                        log.warning("[autofarm] Heartbeat: Stock habis! Membeli ulang...")
                        engine.buy_farmable(farmable_item)
                        screen, msg = engine.goto("home")

                    if not arroz_ok or not benedict_ok:
                        log.warning("[autofarm] Heartbeat: Buff habis! Menjalankan re-buff...")
                        buffs.run(engine, {})
                        screen, msg = engine.goto("home")

                    if engine.read_autofarm_state([msg]) != "ON":
                        _set_autofarm_state(engine, "ON")
                except Exception as exc:
                    log.warning("[autofarm] Kendala saat heartbeat check: %s", exc)
                    try:
                        engine.goto("home")
                    except Exception:
                        pass

                if hasattr(engine, "safe_drain_events"):
                    engine.safe_drain_events()
                else:
                    while engine.gw.pop_event(timeout=0) is not None:
                        pass

    except KeyboardInterrupt:
        log.warning("[autofarm] Dihentikan oleh pengguna (Ctrl+C)")
        raise


def run(engine, args):
    args = args or {}
    mode = (args.get("mode") or "").lower()

    if mode in ("off", "0", "false"):
        return _set_autofarm_state(engine, "OFF")
    if mode in ("toggle",):
        current = engine.read_autofarm_state()
        target = "OFF" if current == "ON" else "ON"
        return _set_autofarm_state(engine, target)
    if mode in ("on", "1", "true"):
        return _set_autofarm_state(engine, "ON")
    if mode in ("once", "check", "prep", "prepare"):
        return _prepare_autofarm(engine)

    # Default: sistem autofarm lengkap + standby listener
    _full_autofarm_loop(engine, args)
