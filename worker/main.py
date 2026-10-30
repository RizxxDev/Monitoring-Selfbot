import argparse
import json
import logging
import re
import sys
import time

import config as cfg
from core.api import Api, ApiError, AuthError, GemsExhaustedError
from core.bot import Engine, NavError
from core.gateway import Gateway
from core.screens import SCREENS, parse_screen
from tasks import TASKS
from tasks.watch import run as run_watch

log = logging.getLogger("growcord.main")


def setup_logging():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        from logging.handlers import RotatingFileHandler
        handlers.append(
            RotatingFileHandler(
                cfg.LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    for name in ("growcord.api", "growcord.gateway"):
        logging.getLogger(name).setLevel(logging.INFO)


def validate_config():
    problems = []
    if not cfg.TOKEN or "ISI_" in cfg.TOKEN:
        problems.append(
            "TOKEN belum diisi.\n  - Buka README.md bagian 'Ambil Token'\n"
            "  - isi di config.py atau set env DISCORD_TOKEN"
        )
    if not str(cfg.CHANNEL_ID).isdigit():
        problems.append(
            "CHANNEL_ID belum diisi (angka).\n"
            "  - Aktifkan Developer Mode: Settings -> Advanced\n"
            "  - Klik kanan thread farm-rizzxgtps -> Copy Channel ID"
        )
    if problems:
        for item in problems:
            log.error(item)
        return False
    return True


def build_engine(channel_check=True):
    api = Api(cfg.TOKEN, cfg.USER_AGENT)
    gw = Gateway(cfg.TOKEN)
    api._session_provider = lambda: gw.session_id if gw else ""
    gw.on_session = lambda sid: setattr(api, "session_id", sid)
    engine = Engine(api, gw, cfg.CHANNEL_ID)
    log.info("menghubungkan gateway discord...")
    gw.start()
    try:
        if not gw.wait_ready(20):
            raise ApiError(
                "gateway tidak READY dalam 20 detik. cek koneksi atau token kamu."
            )
    except ApiError:
        raise
    if gw.fatal:
        raise AuthError("token ditolak oleh gateway (mungkin token tidak valid).")
    log.info("login sukses sebagai %s", gw.user_name)
    if gw.session_id:
        api.session_id = gw.session_id
        log.info("session_id gateway terpasang (interaksi siap)")

    if not channel_check:
        return engine
    try:
        info = api.channel_info(cfg.CHANNEL_ID)
    except ApiError as exc:
        if "403" in str(exc):
            raise ApiError(
                f"channel {cfg.CHANNEL_ID} tidak bisa dibaca (403 Missing Access). "
                f"ID ini kemungkinan bukan thread farm. Jalankan: python main.py find"
            )
        raise
    engine.guild_id = info.get("guild_id", "")
    thread_name = info.get("name", "?")
    log.info("channel tujuan: %s", thread_name)
    return engine


def cmd_status(engine):
    screen, _msg = engine.locate()
    if screen is None:
        log.info("posisi sekarang: tidak dikenal (jalankan python main.py inspect)")
        return
    log.info("posisi sekarang: %s", screen.id)
    gems = engine.read_gems()
    if gems is not None:
        log.info("gems: %s", engine.fmt_int(gems))
    farm = engine.read_autofarm_state()
    if farm:
        log.info("auto farm: %s", farm)


def cmd_nav(engine, target):
    screen, _msg = engine.goto(target)
    log.info("sampai layar: %s", screen.id)


def cmd_inspect(engine, gw, click_key):
    docs = engine.fetch_messages(8)
    print("\n=== PESAN TERAKHIR ===")
    for doc in docs:
        author = (doc.get("author") or {}).get("username", "?")
        text = engine.message_text(doc).replace("\n", " | ")[:110]
        screen = parse_screen(engine.message_text(doc))
        target_name = screen.id if screen else "-"
        token_yes = bool((doc.get("interaction") or {}).get("token"))
        buttons = engine.message_buttons(doc)
        button_desc = ", ".join(
            f"{b['label']}[id={b['custom_id'] or '?'}]" for b in buttons
        )
        print(
            f" #{doc['id'][-6:]} {author:<10} screen={target_name:<6} "
            f"token={'Y' if token_yes else 'N'}\n   text: {text}\n"
            f"   buttons: {button_desc}"
        )

    if not click_key:
        return

    pattern = re.compile(click_key.replace("_", r"[_ ]?"), re.IGNORECASE)
    target_doc = None
    target_comp = None
    for doc in docs:
        for comp in engine.message_buttons(doc):
            if pattern.search(comp["label"]):
                target_doc, target_comp = doc, comp
                break
        if target_doc:
            break
    if target_doc is None:
        print(f"tombol '{click_key}' tidak ditemukan di pesan terakhir")
        return

    print(f"\n=== KLIK [{target_comp['label']}] id={target_comp['custom_id']} ===")
    engine.api.click_button(target_doc, target_comp["custom_id"], engine.guild_id)
    print("interaksi terkirim, pantau event realtime 12 detik...\n")
    deadline = time.time() + 12.0
    while time.time() < deadline:
        event = gw.pop_event(timeout=min(0.5, deadline - time.time()))
        if event is None:
            continue
        kind, data, _ts = event
        if kind == "interaction":
            print("--- INTERACTION_CREATE ---")
            print(eval_safe(data))
        elif kind in ("message_new", "message_edit"):
            print("--- PESAN BOT ---")
            print(engine.message_text(data)[:400].replace("\n", " | "))


def cmd_find(engine, needle, apply=False):
    needle = (needle or "farm").lower()
    print(f'mencari thread/channel "{needle}"...\n')
    matches = []

    for thread in engine.gw.joined_threads():
        if needle in thread["name"].lower():
            matches.append(thread)
            print(
                f'  [THREAD ] {thread["id"]:<20} {thread["name"]:<28} '
                f"server='{thread['guild']}' parent={thread['parent']}"
            )

    if not matches:
        guilds = engine.api.get_guilds()
        gnames = {g["id"]: g.get("name", "?") for g in guilds}
        for gid, gname in gnames.items():
            for chan in engine.api.guild_channels(gid):
                cname = chan.get("name", "")
                if needle in cname.lower():
                    matches.append(
                        {"id": chan["id"], "name": cname, "guild": gname}
                    )
                    print(
                        f"  [CHANNEL] {chan['id']:<20} {cname:<28} server='{gname}'"
                    )

    if not matches:
        print(
            "tidak ketemu.\n"
            " - coba kata lain: python main.py find rizzxgtps\n"
            f" - atau pastikan kamu benar-benar member thread ini; kalau sudah "
            f"keluar thread, isikan CHANNEL_ID manual: klik kanan nama thread "
            f"'farm-rizzxgtps' di sidebar -> Copy Channel ID"
        )
        return

    with_parent = [m for m in matches if m.get("parent")]
    pick = with_parent[0] if with_parent else matches[0]
    print(f'\nkandidat: {pick["id"]} ({pick["name"]})')
    if len(matches) > 1:
        print("(ada beberapa hasil; pilih manual dengan python main.py find farm --apply <id>)")
    if apply:
        target = apply if isinstance(apply, str) and apply.isdigit() else pick["id"]
        if isinstance(apply, str) and apply.isdigit():
            valid = [m for m in matches if str(m["id"]) == apply]
            if not valid:
                print(f"id {apply} tidak termasuk hasil di atas")
                return
        set_channel_id(target)
        print(f"CHANNEL_ID di config.py di-set ke {target}")
        print("test: python main.py status")


def set_channel_id(channel_id):
    with open("config.py", "r", encoding="utf-8") as fh:
        text = fh.read()
    text, count = re.subn(
        r'(CHANNEL_ID\s*=\s*(?:os\.getenv\([^)]*\)\s*or\s*)?)"[^"]*"',
        lambda m: f'{m.group(1)}"{channel_id}"',
        text,
        count=1,
    )
    if count == 0:
        raise RuntimeError("baris CHANNEL_ID tidak ketemu di config.py")
    with open("config.py", "w", encoding="utf-8") as fh:
        fh.write(text)


def eval_safe(data):
    try:
        return indent_json(data)
    except Exception:
        return str(data)[:1500]


def indent_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False)[:2500]


def cmd_list_screens():
    print("Layar tersedia:")
    for screen in SCREENS:
        buttons = ", ".join(f"{key}={label}" for key, label in screen.buttons.items())
        print(f" - {screen.id}:\n     tombol: {buttons}")


def main():
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Growcord selfbot: navigator otomatis + beli WL / auto farm"
    )
    parser.add_argument("command", nargs="?", help="buy_wl | buffs | autofarm | watch | status | nav | inspect | find | screens")
    parser.add_argument("mode", nargs="?", help="autofarm: on/off/toggle; nav: layar; find: kata kunci atau ID")
    parser.add_argument("--amount", "-a", type=int, help="buy_wl/buffs: batas jumlah; watch: jumlah siklus")
    parser.add_argument("--click", "-c", help="inspect: klik tombol ini lalu dump respon raw")
    parser.add_argument(
        "--apply", nargs="?", const=True, default=False,
        help="find: set CHANNEL_ID di config.py `--apply` (otomatis) atau `--apply <id>` (manual)",
    )
    args = parser.parse_args()

    command = (args.command or "").lower()
    if command in ("", "help", "screens"):
        cmd_list_screens()
        print("\nPerintah: buy_wl | buffs | autofarm [on|off|toggle] | watch [--amount N] | status | nav <layar> | inspect [--click <tombol>] | find [kata] [--apply]")
        return

    if not validate_config():
        sys.exit(1)

    engine = build_engine(channel_check=command != "find")
    gw = engine.gw
    try:
        if command == "find" and not gw.fatal:
            log.info("gateway tidak dipakai untuk find, dibatalkan...")
            gw.stop()
        if command == "status":
            cmd_status(engine)
        elif command == "watch":
            run_watch(engine, {"iterations": args.amount or 0})
        elif command == "nav":
            if not args.mode:
                cmd_list_screens()
                return
            cmd_nav(engine, args.mode.lower())
        elif command == "inspect":
            cmd_inspect(engine, gw, args.click)
        elif command == "find":
            needle = args.mode or "farm"
            apply = args.apply
            if not apply and needle.isdigit():
                apply = needle
                needle = "farm"
            cmd_find(engine, needle, apply)
        elif command in TASKS:
            task_args = {}
            if args.amount:
                task_args["amount"] = args.amount
            if command == "autofarm":
                task_args["mode"] = (args.mode or "")
                if not task_args["mode"]:
                    consecutive_errors = 0
                    while True:
                        try:
                            TASKS[command](engine, task_args)
                            break
                        except KeyboardInterrupt:
                            raise
                        except GemsExhaustedError as exc:
                            log.critical(
                                "[KRITIS] GEMS HABIS! %s. Bot dihentikan.",
                                exc,
                            )
                            break
                        except AuthError:
                            raise
                        except Exception as exc:
                            consecutive_errors += 1
                            delay = min(10.0 * consecutive_errors, 60.0)
                            log.error(
                                "[24/7 Supervisor] Terjadi error (%s): %s. Memulai pemulihan otomatis dalam %.0fs...",
                                type(exc).__name__,
                                exc,
                                delay,
                            )
                            try:
                                engine.goto("home")
                            except Exception:
                                pass
                            time.sleep(delay)
                else:
                    TASKS[command](engine, task_args)
            else:
                TASKS[command](engine, task_args)
        else:
            log.error("perintah tidak dikenal: %s", command)
            cmd_list_screens()
            sys.exit(2)
    except NavError as exc:
        log.error("Navigasi gagal: %s", exc)
        sys.exit(2)
    except (AuthError, ApiError) as exc:
        log.error("%s", exc)
        sys.exit(3)
    except KeyboardInterrupt:
        log.warning("dihentikan oleh pengguna")
    finally:
        gw.stop()


if __name__ == "__main__":
    main()
