import logging

import config as cfg
from core.bot import NavError

log = logging.getLogger("growcord.task")


def run(engine, args):
    amount_target = args.pop("amount", None)
    screen, msg = engine.goto("locks")
    gems = engine.read_gems()
    if gems is None:
        raise NavError("tidak bisa membaca 'Gems:' dari embed Locks Toko")
    budget = (gems - cfg.GEM_FLOOR) // cfg.WL_PRICE
    if amount_target:
        budget = min(budget, int(amount_target))
    if budget <= 0:
        log.info(
            "gems tersisa %s sudah di bawah batas %s, tidak ada pembelian",
            engine.fmt_int(gems),
            cfg.GEM_FLOOR,
        )
        return

    cycles = (budget + cfg.MAX_PER_BUY - 1) // cfg.MAX_PER_BUY
    log.info(
        "gems tersedia %s -> target %s WL (%s siklus)",
        engine.fmt_int(gems),
        engine.fmt_int(budget),
        cycles,
    )

    bought = 0
    gems_actual = gems
    for cycle in range(1, cycles + 1):
        quantity = min(cfg.MAX_PER_BUY, budget - bought)
        actual_qty = engine.buy_with_form("locks", "beli_wl", quantity)
        if isinstance(actual_qty, int) and actual_qty > 0:
            quantity = actual_qty
        reply = engine.wait_bot_reply(cfg.REPLY_TIMEOUT)
        reply_read = False
        if reply is not None:
            result = engine.message_text(reply)
            if engine.abort_reason(result):
                raise NavError(
                    "dihentikan, balasan bot: " + result.replace("\n", " ")[:220]
                )
            new_gems = engine.read_gems(reply)
            if new_gems is not None and new_gems < gems_actual:
                gems_actual = new_gems
                reply_read = True
        else:
            log.warning(
                "balasan bot tidak terdeteksi dalam %ss, langsung lanjut",
                cfg.REPLY_TIMEOUT,
            )
        bought += quantity
        if not reply_read:
            gems_actual = max(0, gems_actual - quantity * cfg.WL_PRICE)
        estimate = gems_actual
        log.info(
            "siklus %d/%d -> +%s WL (total %s/%s), sisa gems ~%s",
            cycle,
            cycles,
            quantity,
            bought,
            budget,
            engine.fmt_int(max(estimate, 0)),
        )
        if bought >= budget:
            break
        engine.sleep_min_max(cfg.DELAY_BUY)

    log.info(
        "selesai: total %s WL dibeli, gems tersisa ~%s "
        "(maksimal beli; sisa %s-%s gems di bawah floor %s tidak terjual)",
        bought,
        engine.fmt_int(max(gems_actual, 0)),
        cfg.GEM_FLOOR,
        cfg.GEM_FLOOR + cfg.WL_PRICE - 1,
        cfg.GEM_FLOOR,
    )
