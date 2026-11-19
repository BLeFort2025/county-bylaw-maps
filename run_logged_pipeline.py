"""
run_logged_pipeline.py — Concurrent-safe, real-time logged runner for OFA Municipal Intelligence scans.

Creates:
  logs/weekly_scan_<YYYY-MM-DD_HHMMSS>.log  (or daily_heal_<...>.log)
  logs/latest_weekly_scan.log               (or latest_daily_heal.log)
  logs/latest_run_status.json               (live step/metric/issue JSON snapshot)
  logs/run_history.jsonl                    (append-only run summary ledger)
  logs/pipeline.lock                        (PID concurrency guard across Task Scheduler & manual runs)

Usage:
  python -u run_logged_pipeline.py --mode weekly
  python -u run_logged_pipeline.py --mode daily-heal
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(SCRIPT_DIR, "logs")
LOCK_PATH = os.path.join(LOGS_DIR, "pipeline.lock")
STATUS_PATH = os.path.join(LOGS_DIR, "latest_run_status.json")
HISTORY_PATH = os.path.join(LOGS_DIR, "run_history.jsonl")

WEEKLY_WAIT_TIMEOUT_S = 45 * 60
LOCK_POLL_INTERVAL_S = 10
DUPLICATE_WEEKLY_GUARD_HOURS = 12


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _recent_completed_weekly_run(hours: float = DUPLICATE_WEEKLY_GUARD_HOURS) -> str | None:
    if not os.path.exists(HISTORY_PATH):
        return None
    now = datetime.datetime.now().astimezone()
    recent_id: str | None = None
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except Exception:
                    continue
                if entry.get("mode") != "weekly" or entry.get("status") != "completed":
                    continue
                finished_raw = entry.get("finished_at")
                if not finished_raw:
                    continue
                try:
                    finished_dt = datetime.datetime.fromisoformat(str(finished_raw))
                    if finished_dt.tzinfo is None:
                        finished_dt = finished_dt.replace(tzinfo=now.tzinfo)
                    if (now - finished_dt).total_seconds() < hours * 3600:
                        recent_id = str(entry.get("run_id") or "")
                except Exception:
                    continue
    except Exception:
        return None
    return recent_id


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _is_pid_running_python(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = (res.stdout or "").lower()
        return str(pid) in out and "python" in out
    except Exception:
        return False


def _read_lock() -> dict[str, Any] | None:
    if not os.path.exists(LOCK_PATH):
        return None
    try:
        with open(LOCK_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _acquire_lock(mode: str) -> bool:
    os.makedirs(LOGS_DIR, exist_ok=True)
    deadline = time.monotonic() + WEEKLY_WAIT_TIMEOUT_S
    waited_logged = False

    while True:
        existing = _read_lock()
        if existing is not None:
            old_pid = int(existing.get("pid", -1) or -1)
            if _is_pid_running_python(old_pid):
                if mode == "daily-heal":
                    print(
                        f"Another pipeline is running (PID {old_pid}, mode={existing.get('mode')}); "
                        "skipping daily-heal.",
                        flush=True,
                    )
                    return False
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Timed out after {WEEKLY_WAIT_TIMEOUT_S}s waiting for pipeline PID {old_pid}"
                    )
                if not waited_logged:
                    print(
                        f"Another pipeline is running (PID {old_pid}, mode={existing.get('mode')}); "
                        "waiting up to 45 minutes for it to finish...",
                        flush=True,
                    )
                    waited_logged = True
                time.sleep(LOCK_POLL_INTERVAL_S)
                continue
        break

    payload = {
        "pid": os.getpid(),
        "mode": mode,
        "started_at": _now_iso(),
    }
    with open(LOCK_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return True


def _release_lock() -> None:
    existing = _read_lock()
    if existing is None or int(existing.get("pid", -1) or -1) == os.getpid():
        try:
            if os.path.exists(LOCK_PATH):
                os.remove(LOCK_PATH)
        except Exception:
            pass


def _atomic_write_json(path: str, data: dict[str, Any]) -> None:
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp_path, path)


class PipelineLogger:
    """Mirrors output to timestamped + latest logs while maintaining latest_run_status.json."""

    def __init__(self, mode: str) -> None:
        os.makedirs(LOGS_DIR, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        prefix = "weekly_scan" if mode == "weekly" else "daily_heal"
        self.run_id = f"{mode.replace('-', '_')}_{ts}"
        self.archive_log = os.path.join(LOGS_DIR, f"{prefix}_{ts}.log")
        self.latest_log = os.path.join(LOGS_DIR, f"latest_{prefix}.log")

        self._f_arch = open(self.archive_log, "w", encoding="utf-8", errors="replace")
        self._f_latest = open(self.latest_log, "w", encoding="utf-8", errors="replace")
        self._line_counter = 0

        self.status_doc: dict[str, Any] = {
            "run_id": self.run_id,
            "mode": mode,
            "pid": os.getpid(),
            "status": "running",
            "started_at": _now_iso(),
            "updated_at": _now_iso(),
            "log_file": self.archive_log,
            "latest_log_file": self.latest_log,
            "current_step": "initializing",
            "metrics": {
                "prefetch_munis_ok": 0,
                "prefetch_docs_cached": 0,
                "prefetch_failed": 0,
                "v1_hits": 0,
                "v2_hits": 0,
            },
            "issues": [],
            "steps": [],
        }
        self.flush_status()

    def close(self) -> None:
        for fh in (self._f_arch, self._f_latest):
            try:
                fh.flush()
                fh.close()
            except Exception:
                pass

    def flush_status(self) -> None:
        self.status_doc["updated_at"] = _now_iso()
        _atomic_write_json(STATUS_PATH, self.status_doc)

    def write_line(self, line: str, step_label: str = "") -> None:
        clean = line.rstrip("\r\n")
        print(clean, flush=True)
        for fh in (self._f_arch, self._f_latest):
            fh.write(clean + "\n")
            fh.flush()

        self._line_counter += 1
        dirty = self._inspect_line(clean, step_label)
        if dirty or self._line_counter % 20 == 0:
            self.flush_status()

    def _inspect_line(self, line: str, step_label: str) -> bool:
        dirty = False
        metrics = self.status_doc["metrics"]

        if step_label.startswith("[1/"):
            m_ok = re.search(r"^\[\d+/\d+\]\s+.+\.\.\.\s+OK\s+\((\d+)\s+doc", line)
            if m_ok:
                metrics["prefetch_munis_ok"] += 1
                metrics["prefetch_docs_cached"] += int(m_ok.group(1))
                dirty = True
            elif "-- no docs found" in line:
                metrics["prefetch_failed"] += 1
                dirty = True
            m_sum_ok = re.search(r"Municipalities with docs:\s*(\d+)/(\d+)", line)
            if m_sum_ok:
                metrics["prefetch_munis_ok"] = int(m_sum_ok.group(1))
                dirty = True
            m_sum_docs = re.search(r"Total documents cached:\s*(\d+)", line)
            if m_sum_docs:
                metrics["prefetch_docs_cached"] = int(m_sum_docs.group(1))
                dirty = True
            m_sum_fail = re.search(r"Failed/no docs:\s*(\d+)", line)
            if m_sum_fail:
                metrics["prefetch_failed"] = int(m_sum_fail.group(1))
                dirty = True

        if "[!] HIT:" in line:
            if step_label.startswith("[3/"):
                metrics["v1_hits"] += 1
            elif step_label.startswith("[4/"):
                metrics["v2_hits"] += 1
            dirty = True

        m_v1_total = re.search(r"SUCCESS:\s*Found\s*(\d+)\s*candidate hits", line)
        if m_v1_total and step_label.startswith("[3/"):
            metrics["v1_hits"] = int(m_v1_total.group(1))
            dirty = True

        m_v2_total = re.search(r"Selenium found\s*(\d+)\s*NEW candidate hits", line)
        if m_v2_total and step_label.startswith("[4/"):
            metrics["v2_hits"] = int(m_v2_total.group(1))
            dirty = True

        issue_markers = (
            "ERROR:",
            "Traceback",
            "PermissionError",
            "WebDriverException",
            "FAILED (",
            "-- no docs found",
            "[AI Error:",
        )
        if any(marker in line for marker in issue_markers):
            issues = self.status_doc["issues"]
            if len(issues) < 500:
                issues.append(
                    {
                        "timestamp": _now_iso(),
                        "step": step_label or self.status_doc["current_step"],
                        "message": line[:300],
                    }
                )
            dirty = True

        return dirty

    def start_step(self, label: str) -> dict[str, Any]:
        self.status_doc["current_step"] = label
        entry = {
            "step": label,
            "status": "running",
            "started_at": _now_iso(),
            "finished_at": None,
            "exit_code": None,
        }
        self.status_doc["steps"].append(entry)
        self.flush_status()
        self.write_line(f"=== {label} ===", label)
        return entry

    def finish_step(self, entry: dict[str, Any], exit_code: int) -> None:
        entry["finished_at"] = _now_iso()
        entry["exit_code"] = exit_code
        entry["status"] = "completed" if exit_code == 0 else "failed"
        if exit_code != 0:
            self.status_doc["issues"].append(
                {
                    "timestamp": _now_iso(),
                    "step": entry["step"],
                    "message": f"Step exited with code {exit_code}",
                }
            )
        self.flush_status()

    def run_cmd(self, cmd: list[str], step_label: str) -> int:
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.Popen(
            cmd,
            cwd=SCRIPT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            self.write_line(line, step_label)
        return proc.wait()

    def git_sync(self, files: list[str], message: str, step_label: str) -> None:
        existing = [f for f in files if os.path.exists(os.path.join(SCRIPT_DIR, f))]
        if not existing:
            self.write_line(f"Git sync skipped (no target files found): {files}", step_label)
            return

        self.run_cmd(["git", "add", *existing], step_label)
        # Check if anything is actually staged
        diff_res = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=SCRIPT_DIR,
        )
        if diff_res.returncode == 0:
            self.write_line("nothing to commit, working tree clean", step_label)
            return

        rc_commit = self.run_cmd(["git", "commit", "-m", message], step_label)
        if rc_commit == 0:
            self.run_cmd(["git", "push", "origin", "HEAD:staging-expiry-signals"], step_label)
            self.run_cmd(["git", "push", "origin", "HEAD:main"], step_label)

    def finalize(self, overall_status: str) -> None:
        self.status_doc["status"] = overall_status
        self.status_doc["current_step"] = "done"
        self.status_doc["finished_at"] = _now_iso()
        self.flush_status()

        summary = {
            "run_id": self.run_id,
            "mode": self.status_doc["mode"],
            "status": overall_status,
            "started_at": self.status_doc["started_at"],
            "finished_at": self.status_doc["finished_at"],
            "log_file": self.archive_log,
            "metrics": self.status_doc["metrics"],
            "issue_count": len(self.status_doc["issues"]),
            "steps": self.status_doc["steps"],
        }
        with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary) + "\n")


def _clean_intermediate_files(logger: PipelineLogger, step_label: str) -> int:
    patterns = [
        os.path.join(SCRIPT_DIR, "signals", "candidates_*.csv"),
        os.path.join(SCRIPT_DIR, "signals", "coverage_report_*.csv"),
        os.path.join(SCRIPT_DIR, "candidates_*.csv"),
        os.path.join(SCRIPT_DIR, "coverage_report_*.csv"),
    ]
    removed = 0
    for pat in patterns:
        for path in glob.glob(pat):
            try:
                os.remove(path)
                removed += 1
            except Exception as exc:
                logger.write_line(f"ERROR: Could not remove {path}: {exc}", step_label)
    logger.write_line(f"Removed {removed} intermediate candidate/coverage file(s).", step_label)
    return 0


def run_weekly(logger: PipelineLogger) -> int:
    logger.write_line("==========================================", "header")
    logger.write_line("     STARTING WEEKLY INTELLIGENCE SCAN    ", "header")
    logger.write_line("==========================================", "header")

    critical_failed = False

    # [0/8] Refresh non-JS registry URLs + git sync
    lbl = "[0/8] Refreshing non-JS portal registry URLs"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "refresh_registry.py", "--non-js"], lbl)
    logger.git_sync(["signals/portal_registry.csv"], "auto: weekly refresh of portal registry URLs", lbl)
    logger.finish_step(st, rc)

    # [1/8] Selenium Pre-Fetch of JS portals + git sync
    lbl = "[1/8] Pre-fetching document text from JS-rendered portals"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "selenium_prefetch.py"], lbl)
    if rc != 0:
        critical_failed = True
    logger.git_sync(
        ["signals/cached_portal_docs.csv", "signals/portal_registry.csv"],
        "auto: weekly Selenium pre-fetch of JS portal documents",
        lbl,
    )
    logger.finish_step(st, rc)

    # [2/8] Clean intermediate candidate/coverage CSVs
    lbl = "[2/8] Cleaning old intermediate candidate files"
    st = logger.start_step(lbl)
    rc = _clean_intermediate_files(logger, lbl)
    logger.finish_step(st, rc)

    # [3/8] Scanner V1 (HTML + PDF + persists non-JS full text into unified cache)
    lbl = "[3/8] Running Scanner V1 (HTML and PDF)"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "scanner_v1_robust.py"], lbl)
    if rc != 0:
        critical_failed = True
    logger.finish_step(st, rc)

    # [4/8] Scanner V2 (Selenium for failures + persists retried full text into unified cache)
    lbl = "[4/8] Running Scanner V2 (Selenium for failures)"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "scanner_v2_selenium.py"], lbl)
    if rc != 0:
        critical_failed = True
    logger.finish_step(st, rc)

    # [5/8] Generate signals & sync SQLite/Postgres
    lbl = "[5/8] Merging intelligence and syncing SQLite/PostgreSQL"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "generate_signals.py"], lbl)
    if rc != 0:
        critical_failed = True
    logger.finish_step(st, rc)

    # [6/8] Send County Federation Weekly Digests (OFA-branded emails + BCC ben.lefort@ofa.on.ca)
    lbl = "[6/8] Sending County Federation Weekly Digests"
    st = logger.start_step(lbl)
    rc_digest = logger.run_cmd([sys.executable, "-u", "county_digest_mailer.py"], lbl)
    if rc_digest != 0:
        logger.write_line(f"WARNING: County digest mailer exited with code {rc_digest}", lbl)
    logger.finish_step(st, rc_digest)

    # [7/8] Push updated signals & unified 444-municipality text cache to GitHub
    lbl = "[7/8] Pushing updated signals & unified council cache to GitHub"
    st = logger.start_step(lbl)
    logger.git_sync(
        ["signals/signals.csv", "signals/cached_portal_docs.csv", "signals/portal_registry.csv"],
        "auto: weekly intelligence scan results & unified council cache",
        lbl,
    )
    logger.finish_step(st, 0)

    logger.write_line("==========================================", "footer")
    logger.write_line("     WEEKLY SCAN COMPLETE                 ", "footer")
    logger.write_line("==========================================", "footer")

    logger.finalize("failed" if critical_failed else "completed")
    return 1 if critical_failed else 0


def run_daily_heal(logger: PipelineLogger) -> int:
    logger.write_line("==========================================", "header")
    logger.write_line("     STARTING DAILY AUTO-HEAL SCAN        ", "header")
    logger.write_line("==========================================", "header")

    lbl = "[daily-heal] Refreshing portal registry URLs"
    st = logger.start_step(lbl)
    rc = logger.run_cmd([sys.executable, "-u", "refresh_registry.py"], lbl)
    logger.git_sync(["signals/portal_registry.csv"], "auto: daily auto-heal of municipal portal registry URLs", lbl)
    logger.finish_step(st, rc)

    logger.finalize("failed" if rc != 0 else "completed")
    return rc


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description="Logged OFA Municipal Intelligence pipeline runner.")
    parser.add_argument("--mode", choices=["weekly", "daily-heal"], required=True)
    parser.add_argument("--force", action="store_true", help="Run weekly scan even if completed within 12h")
    args = parser.parse_args()

    if args.mode == "weekly" and not args.force:
        recent_id = _recent_completed_weekly_run()
        if recent_id:
            print(
                f"Weekly scan already completed within last {DUPLICATE_WEEKLY_GUARD_HOURS}h ({recent_id}); "
                "skipping duplicate scheduled trigger.",
                flush=True,
            )
            return 0

    if not _acquire_lock(args.mode):
        return 0

    logger = PipelineLogger(args.mode)
    try:
        if args.mode == "weekly":
            return run_weekly(logger)
        return run_daily_heal(logger)
    except Exception as exc:
        logger.write_line(f"ERROR: Unhandled pipeline exception: {exc}", logger.status_doc["current_step"])
        logger.finalize("failed")
        return 1
    finally:
        logger.close()
        _release_lock()


if __name__ == "__main__":
    sys.exit(main())
