"""newsbrief CLI entrypoint."""
from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger("newsbrief")

_DESCRIPTION = "newsbrief — Self-hosted AI news digest for Telegram"
_EPILOG = """\
Examples:
  newsbrief setup            Interactive setup (5 questions)
  newsbrief doctor           Check all connections
  newsbrief run              Build and send now
  newsbrief dry-run          Preview without sending
  newsbrief daemon           Run with scheduler (docker)
  newsbrief sources list     Show configured sources
  newsbrief sources validate Check each source is reachable
  newsbrief stats --days 30  Show 30-day statistics
  newsbrief pause --days 3   Pause deliveries for 3 days
  newsbrief resume           Resume deliveries

Get started: newsbrief setup
Docs: https://github.com/newsbrief/newsbrief
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="newsbrief",
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print tracebacks on unexpected errors")
    sub = parser.add_subparsers(dest="command", required=False)

    sub.add_parser("setup",    help="Interactive setup wizard (5 questions)")
    sub.add_parser("doctor",   help="Run diagnostics on all components")
    sub.add_parser("discover", help="Re-run source discovery wizard")
    p_sch = sub.add_parser("schedule", help="Change delivery time")
    p_sch.add_argument("--preset", help="Non-interactive HH:MM time")
    p_sch.add_argument("--blocks", action="store_true",
                       help="Manage interest blocks (list)")
    sub.add_parser("validate", help="Validate config")
    sub.add_parser("dry-run",  help="Generate digest without sending")
    sub.add_parser("run",      help="One-off run (build + send)")
    sub.add_parser("daemon",   help="Run with scheduler (for docker)")

    p_pause = sub.add_parser("pause", help="Pause deliveries for N days")
    p_pause.add_argument("--days", type=int, default=1,
                         help="Days to pause (default: 1)")

    sub.add_parser("resume",   help="Resume deliveries")
    sub.add_parser("version",  help="Show version")

    llm = sub.add_parser("llm", help="LLM management")
    llm_sub = llm.add_subparsers(dest="llm_cmd")
    llm_sub.add_parser("setup")
    llm_sub.add_parser("list")
    llm_sub.add_parser("test")
    p_sw = llm_sub.add_parser("switch", help="Switch active provider")
    p_sw.add_argument("provider_id")
    p_add = llm_sub.add_parser("add", help="Add a new provider (interactive)")
    p_add.add_argument("preset", nargs="?", default=None)
    p_rm = llm_sub.add_parser("remove", help="Remove a provider")
    p_rm.add_argument("provider_id")

    srcs = sub.add_parser("sources", help="Sources management")
    srcs_sub = srcs.add_subparsers(dest="src_cmd")
    srcs_sub.add_parser("list",     help="Show configured sources")
    srcs_sub.add_parser("validate", help="Check each source is reachable")
    srcs_sub.add_parser("suggest",  help="Run discovery wizard for more sources")
    p_sadd = srcs_sub.add_parser("add", help="Add a source to a topic")
    p_sadd.add_argument("topic")
    p_sadd.add_argument("type")
    p_sadd.add_argument("config_val", help="URL/sub/channel for the source")
    p_srem = srcs_sub.add_parser("remove", help="Remove a source from a topic")
    p_srem.add_argument("topic")
    p_srem.add_argument("url")

    p_stats = sub.add_parser("stats", help="Weekly/monthly statistics")
    p_stats.add_argument("--days", type=int, default=7,
                         help="Period in days (default: 7)")
    p_stats.add_argument("--format", choices=["text", "json"], default="text",
                         help="Output format")

    p_cfg = sub.add_parser("config", help="Config management")
    p_cfg_sub = p_cfg.add_subparsers(dest="config_cmd")
    p_cfg_sub.add_parser("show",     help="Print config.yaml with secrets redacted")
    p_cfg_sub.add_parser("edit",     help="Open config.yaml in $EDITOR")
    p_cfg_sub.add_parser("validate", help="Validate config")
    p_cfg_sub.add_parser("export",   help="Export config as JSON")
    p_cfg_imp = p_cfg_sub.add_parser("import", help="Import JSON into config.yaml")
    p_cfg_imp.add_argument("file")

    p_logs = sub.add_parser("logs", help="Show newsbrief logs")
    p_logs.add_argument("--tail", type=int, default=100)
    p_logs.add_argument("--follow", action="store_true")
    p_logs.add_argument("--pipeline", action="store_true")
    p_logs.add_argument("--errors", action="store_true")

    p_bk = sub.add_parser("backup", help="Backup config.yaml + data/ into tar.gz")
    p_bk.add_argument("--output", help="Output path")
    p_rs = sub.add_parser("restore", help="Restore from backup archive")
    p_rs.add_argument("archive")

    p_comp = sub.add_parser("completion", help="Shell completion script")
    p_comp.add_argument("shell", choices=["bash", "zsh", "fish"])

    fb = sub.add_parser("feedback", help="Feedback stats and tools")
    fb_sub = fb.add_subparsers(dest="fb_cmd")
    fb_sub.add_parser("stats")

    ln = sub.add_parser("learn", help="Apply feedback learning")
    ln_sub = ln.add_subparsers(dest="learn_cmd")
    ln_sub.add_parser("apply")

    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except FileNotFoundError as e:
        from newsbrief.utils.cli_output import error
        error(f"Not found: {e}. Did you run `newsbrief setup`?")
        return 1
    except ConnectionError as e:
        from newsbrief.utils.cli_output import error
        error(f"Network error: {e}")
        return 2
    except Exception as e:  # noqa: BLE001
        from newsbrief.utils.cli_output import error
        error(f"Unexpected error: {e}")
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        return 1


def _dispatch(args) -> int:
    cmd = args.command
    if cmd == "version":
        from newsbrief import __version__
        print(f"newsbrief {__version__}")
        return 0

    if cmd == "setup":
        from newsbrief.bot.setup_wizard import run_setup
        return run_setup()

    if cmd == "doctor":
        from newsbrief.core.doctor import run_doctor
        return run_doctor()

    if cmd == "validate":
        from newsbrief.config import get_config
        try:
            cfg = get_config()
            print("✅ Config valid")
            print(f"   Topics: {len(cfg.topics)}")
            print(f"   LLM preset: {cfg.llm.preset or 'custom'}")
            print(f"   Send at: {cfg.schedule.send_at}")
            return 0
        except Exception as e:
            print(f"❌ Config invalid: {e}")
            return 1

    if cmd in ("run", "dry-run"):
        from newsbrief.config import get_config
        from newsbrief.core.storage import get_storage
        from newsbrief.core.pipeline import run_pipeline
        cfg = get_config()
        storage = get_storage()
        send = cmd == "run"
        res = run_pipeline(cfg, storage, llm_router=None, send=send)
        if cmd == "dry-run":
            print(res.get("full_text", "") or "(empty digest)")
        print(
            f"[{cmd}] success={res['success']} items={res['item_count']} "
            f"parts={res['parts']} duration={res['duration_sec']:.1f}s"
        )
        if res.get("error"):
            print(f"  error: {res['error']}")
            return 1
        return 0

    if cmd == "daemon":
        import time as _t
        from newsbrief.config import get_config
        from newsbrief.core.storage import get_storage
        from newsbrief.core.pipeline import run_pipeline
        from newsbrief.core.scheduler import build_scheduler
        cfg = get_config()
        storage = get_storage()

        def _on_build():
            run_pipeline(cfg, storage, llm_router=None, send=False)

        def _on_send():
            run_pipeline(cfg, storage, llm_router=None, send=True)

        sched = build_scheduler(cfg, on_build=_on_build, on_send=_on_send, storage=storage)
        sched.start()
        logger.info("[daemon] scheduler started — Ctrl-C to exit")
        try:
            while True:
                _t.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            sched.shutdown(wait=False)
            logger.info("[daemon] stopped")
        return 0

    if cmd == "schedule":
        from newsbrief.config import get_config
        from newsbrief.core.scheduler import calculate_build_time
        cfg = get_config()
        if getattr(args, "blocks", False):
            print("Interest blocks (MVP): feature placeholder — see config.topics.")
            for t in cfg.topics:
                print(f"  • {t.id}: {t.name}")
            return 0
        preset = getattr(args, "preset", None)
        if preset:
            new_time = preset.strip()
        else:
            print(f"Current send_at: {cfg.schedule.send_at}")
            new_time = input("New delivery time (HH:MM, empty to cancel): ").strip()
        if not new_time:
            print("Cancelled.")
            return 0
        try:
            hh, mm = new_time.split(":")
            int(hh); int(mm)
        except Exception:
            print("Invalid time format.")
            return 1
        cfg.schedule.send_at  = new_time
        cfg.schedule.build_at = calculate_build_time(
            send_at=new_time,
            llm_preset=cfg.llm.preset,
            override_buffer=cfg.schedule.build_buffer_minutes,
        )
        cfg.save()
        print(f"Updated: send_at={new_time} build_at={cfg.schedule.build_at}")
        return 0

    if cmd == "discover":
        from newsbrief.config import TopicConfig, get_config
        from newsbrief.discovery.wizard import run_discovery_wizard
        from newsbrief.llm.router import LLMRouter
        cfg = get_config()
        try:
            router = LLMRouter(cfg)
        except Exception as e:
            print(f"❌ LLM not configured: {e}")
            return 1
        topics = run_discovery_wizard(cfg, router)
        if not topics:
            return 1
        cfg.topics = [TopicConfig.model_validate(t) for t in topics]
        cfg.save()
        print("✅ Saved to config.yaml")
        return 0

    if cmd == "feedback":
        from newsbrief.core.storage import get_storage
        from newsbrief.feedback.collector import get_feedback_stats
        storage = get_storage()
        stats = get_feedback_stats(storage, days=30)
        ratings = stats["source_ratings"]
        if not ratings:
            print("No feedback recorded yet.")
            return 0
        print(f"Feedback over last 30 days ({len(ratings)} sources):")
        print(f"{'source':<30} {'up':>4} {'down':>5} {'blk':>4} {'save':>5} {'score':>7}")
        for src, b in sorted(ratings.items(), key=lambda kv: kv[1]["score"], reverse=True):
            print(
                f"{src[:30]:<30} {b['up']:>4} {b['down']:>5} "
                f"{b['blocked']:>4} {b['saved']:>5} {b['score']:>7.3f}"
            )
        if stats["top_sources"]:
            print(f"\nTop: {', '.join(stats['top_sources'][:5])}")
        if stats["bottom_sources"]:
            print(f"Bottom: {', '.join(stats['bottom_sources'][:5])}")
        return 0

    if cmd == "learn":
        from newsbrief.config import get_config
        from newsbrief.core.storage import get_storage
        from newsbrief.feedback.learner import apply_learning
        cfg = get_config()
        storage = get_storage()
        report = apply_learning(storage, cfg)
        print("Learning suggestions:")
        print(f"  Boosted sources:  {report['boosted'] or '(none)'}")
        print(f"  Demoted sources:  {report['demoted'] or '(none)'}")
        print(f"  Auto-blacklist:   {report['auto_blacklisted'] or '(none)'}")
        return 0

    if cmd == "llm":
        from newsbrief.llm.cli import dispatch as llm_dispatch
        return llm_dispatch(
            getattr(args, "llm_cmd", None),
            provider_id=getattr(args, "provider_id", None),
            preset=getattr(args, "preset", None),
        )

    if cmd == "sources":
        sub_cmd = getattr(args, "src_cmd", None)
        if sub_cmd == "list":
            from newsbrief.cli_sources import cmd_sources_list
            return cmd_sources_list()
        if sub_cmd == "validate":
            from newsbrief.cli_sources import cmd_sources_validate
            return cmd_sources_validate()
        if sub_cmd == "suggest":
            return _dispatch(argparse.Namespace(command="discover"))
        if sub_cmd == "add":
            return _sources_add(args.topic, args.type, args.config_val)
        if sub_cmd == "remove":
            return _sources_remove(args.topic, args.url)
        print("Usage: newsbrief sources {list|validate|suggest|add|remove}")
        return 1

    if cmd == "stats":
        if getattr(args, "format", "text") == "json":
            import json as _json
            from newsbrief.core.storage import get_storage
            from newsbrief.utils.stats import compute_stats
            print(_json.dumps(compute_stats(get_storage(), days=getattr(args, "days", 7)),
                              ensure_ascii=False, indent=2))
            return 0
        from newsbrief.cli_stats import cmd_stats
        return cmd_stats(days=getattr(args, "days", 7))

    if cmd == "config":
        return _cmd_config(args)

    if cmd == "logs":
        return _cmd_logs(args)

    if cmd == "backup":
        from newsbrief.utils.backup import create_backup
        from newsbrief.utils.cli_output import success
        out = create_backup(output=getattr(args, "output", None))
        success(f"Backup created: {out}")
        return 0

    if cmd == "restore":
        from newsbrief.utils.backup import restore_backup
        from newsbrief.utils.cli_output import success
        restore_backup(args.archive)
        success(f"Restored from {args.archive}")
        return 0

    if cmd == "completion":
        return _cmd_completion(args)

    if cmd == "pause":
        from newsbrief.cli_pause import cmd_pause
        return cmd_pause(days=getattr(args, "days", 1))

    if cmd == "resume":
        from newsbrief.cli_pause import cmd_resume
        return cmd_resume()

    print(f"[{cmd}] not implemented yet")
    return 0


# ---------------------------------------------------------------------------
# Extra command helpers (config / logs / sources add-remove / completion)
# ---------------------------------------------------------------------------

def _cmd_config(args) -> int:
    from newsbrief.utils import config_ops
    from newsbrief.utils.cli_output import console, success, error, info
    sub = getattr(args, "config_cmd", None)
    if sub == "show":
        try:
            console.print(config_ops.redacted_yaml())
            return 0
        except FileNotFoundError:
            error("config.yaml not found. Run: newsbrief setup")
            return 1
    if sub == "edit":
        return config_ops.open_in_editor()
    if sub == "validate":
        from newsbrief.config import get_config
        try:
            cfg = get_config()
            success(f"Config valid (topics={len(cfg.topics)})")
            return 0
        except Exception as e:  # noqa: BLE001
            error(f"Config invalid: {e}")
            return 1
    if sub == "export":
        try:
            print(config_ops.export_json())
            return 0
        except FileNotFoundError:
            error("config.yaml not found.")
            return 1
    if sub == "import":
        config_ops.import_json(args.file)
        success(f"Imported {args.file} → config.yaml")
        return 0
    info("Usage: newsbrief config {show|edit|validate|export|import <file>}")
    return 1


def _cmd_logs(args) -> int:
    import subprocess
    from pathlib import Path
    from newsbrief.utils.cli_output import info, warn
    candidates = [
        Path.home() / ".newsbrief" / "logs",
        Path("logs"),
        Path("data") / "logs",
    ]
    log_dir = next((p for p in candidates if p.exists() and p.is_dir()), None)
    if log_dir is None:
        warn("No log directory found (~/.newsbrief/logs, ./logs, ./data/logs).")
        info("If running under Docker: `docker logs newsbrief`.")
        return 0
    files = sorted(log_dir.glob("*.log"))
    if not files:
        warn(f"No .log files in {log_dir}")
        return 0
    target = str(files[-1])
    if args.follow:
        return subprocess.call(["tail", "-f", target])
    cmd = ["tail", "-n", str(args.tail), target]
    if args.errors or args.pipeline:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)
        assert proc.stdout is not None
        needle = "error" if args.errors else "pipeline"
        for line in proc.stdout:
            if needle in line.lower():
                print(line, end="")
        return proc.wait()
    return subprocess.call(cmd)


def _sources_add(topic_id: str, stype: str, cfg_val: str) -> int:
    from newsbrief.config import get_config
    from newsbrief.utils.cli_output import success, error
    cfg = get_config()
    target = next((t for t in cfg.topics if t.id == topic_id), None)
    if target is None:
        error(f"Topic '{topic_id}' not found.")
        return 1
    entries = target.sources.get(stype) or []
    if not isinstance(entries, list):
        entries = [entries]
    if stype == "rss":
        entries.append(cfg_val)
    elif stype == "telegram":
        entries.append(cfg_val.lstrip("@"))
    elif stype == "reddit":
        entries.append({"subreddit": cfg_val})
    elif stype == "youtube":
        entries.append(cfg_val)
    else:
        entries.append(cfg_val)
    target.sources[stype] = entries
    cfg.save()
    success(f"Added {stype}:{cfg_val} to topic {topic_id}")
    return 0


def _sources_remove(topic_id: str, needle: str) -> int:
    from newsbrief.config import get_config
    from newsbrief.utils.cli_output import success, error
    cfg = get_config()
    target = next((t for t in cfg.topics if t.id == topic_id), None)
    if target is None:
        error(f"Topic '{topic_id}' not found.")
        return 1

    def _match(entry) -> bool:
        if isinstance(entry, str):
            return needle in entry
        if isinstance(entry, dict):
            return any(isinstance(v, str) and needle in v for v in entry.values())
        return False

    removed = 0
    for stype, entries in list((target.sources or {}).items()):
        if isinstance(entries, list):
            new = [e for e in entries if not _match(e)]
            removed += len(entries) - len(new)
            target.sources[stype] = new
    if removed:
        cfg.save()
        success(f"Removed {removed} source(s) from {topic_id}")
        return 0
    error(f"No source matching '{needle}' in {topic_id}")
    return 1


_COMPLETION = {
    "bash": """# bash completion for newsbrief
_newsbrief() {
  local cur cmds
  COMPREPLY=()
  cur="${COMP_WORDS[COMP_CWORD]}"
  cmds="setup doctor discover schedule validate dry-run run daemon llm sources stats pause resume config logs backup restore completion feedback learn version"
  COMPREPLY=( $(compgen -W "${cmds}" -- ${cur}) )
}
complete -F _newsbrief newsbrief
""",
    "zsh": """#compdef newsbrief
_newsbrief() {
  local -a cmds
  cmds=(setup doctor discover schedule validate dry-run run daemon llm sources stats pause resume config logs backup restore completion feedback learn version)
  _describe 'command' cmds
}
_newsbrief "$@"
""",
    "fish": """complete -c newsbrief -f -a "setup doctor discover schedule validate dry-run run daemon llm sources stats pause resume config logs backup restore completion feedback learn version"
""",
}


def _cmd_completion(args) -> int:
    print(_COMPLETION[args.shell])
    return 0


if __name__ == "__main__":
    sys.exit(main())
