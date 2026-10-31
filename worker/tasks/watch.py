import logging

import config as cfg
from core.bot import NavError
from tasks import autofarm, buffs, buy_wl

log = logging.getLogger("growcord.task")


def _one_cycle(engine):
    # 1. Cek stock farmable
    screen, msg = engine.goto("home")
    stock = engine.read_farmable_stock(msg)
    if stock is not None and stock <= 0:
        farmable_item = getattr(engine, "farmable_item", None) or getattr(cfg, "FARMABLE_ITEM", "Pot O' Gems")
        log.warning("[watch] Stock farmable kosong (%s) -> Beli %s", stock, farmable_item)
        engine.buy_farmable(farmable_item)

    # 2. Periksa & konsumsi buff
    buffs.run(engine, {})

    # 3. Cek gems & beli WL jika di atas ambang
    screen, msg = engine.goto("locks")
    gems = engine.read_gems(msg)
    if gems is not None:
        log.info("[watch] gems: %s", engine.fmt_int(gems))
    else:
        log.warning("[watch] gems tidak terbaca di layar locks")

    threshold = int(cfg.WATCH_BUY_GEMS or 0)
    if gems is not None and gems > threshold:
        log.info("[watch] gems di atas ambang %s -> beli WL", engine.fmt_int(threshold))
        buy_wl.run(engine, {})
    else:
        log.info("[watch] gems di bawah ambang, skip buy_wl")

    # 4. Pastikan auto farm ON
    state = engine.read_autofarm_state()
    if state != "ON":
        log.info("[watch] auto farm %s -> dihidupkan", state or "tidak terbaca")
        autofarm.run(engine, {"mode": "on"})
    else:
        log.info("[watch] auto farm masih ON")


def run(engine, args):
    args = args or {}
    iterations = int(args.get("iterations") or cfg.WATCH_ITERATIONS)
    jeda = float(args.get("minutes") or cfg.WATCH_MINUTES) * 60.0
    log.info(
        "[watch] mulai: siklus %s, jeda %.0f menit",
        "tanpa batas" if not iterations else str(iterations),
        jeda / 60.0,
    )

    # Tangani anti-afk tertunda jika ada
    engine.check_recent_anti_afk()

    gagal = 0
    n = 0
    while True:
        n += 1
        log.info("===== watch siklus %d =====", n)
        try:
            _one_cycle(engine)
            gagal = 0
        except NavError as exc:
            gagal += 1
            log.error("[watch] siklus %d gagal: %s", n, exc)
        except Exception as exc:
            gagal += 1
            log.error("[watch] siklus %d error: %r", n, exc)

        if iterations and n >= iterations:
            log.info("watch selesai (%d siklus)", n)
            return
        if gagal >= 3:
            raise RuntimeError("watch gagal %d siklus berturut-turut" % gagal)

        log.info("[watch] Menunggu %.1f menit menuju siklus berikutnya (anti-AFK aktif)...", jeda / 60.0)
        # Gunakan wait_idle agar bot tetap responsif terhadap event 'are you still there?'
        engine.wait_idle(jeda)
