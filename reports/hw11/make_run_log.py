"""Builds reports/hw11/RUN_LOG.txt from the real output files in raw/ (each section headed with the file's modification time, local time)."""
import datetime
import pathlib

HW = pathlib.Path(__file__).resolve().parent
RAW = HW / "raw"
SECTIONS = [
    ("Part 1: kit install and demo test on Muse (pasted from the Muse chat)", "p1_install_output.txt"),
    ("Part 1: standing instructions saved to Muse memory (Muse reply)", "p1_memory_reply.txt"),
    ("Part 1: FIRST live run, kit v1 (reported 0 new)", "p1_first_run.txt"),
    ("Part 1: trace of that run showing both source errors (Muse)", "p1_first_run_trace.txt"),
    ("Part 1: why the sources failed (local curl checks)", "p1_source_diagnosis.txt"),
    ("Part 1: live run after the fixes (kit v2)", "p1_first_run_v2.txt"),
    ("Part 2: volatility study (real Yahoo data)", "vol_study.json"),
    ("Part 4.2: crash, --stop-after 2 (Muse)", "f2_crash.txt"),
    ("Part 4.2: restart in a new chat (Muse)", "f2_restart.txt"),
    ("Part 4.2: resumed run on fixtures/hw11 (Muse)", "f3_resume.txt"),
    ("Part 4.1: trace of the duplicated filing (Muse)", "f1_duplicate_trace.json"),
    ("Part 4: retried alert (Muse)", "r2_retry.txt"),
    ("Part 4: trace of the retried alert's effect (Muse)", "r2_retry_trace.json"),
    ("Part 4.3: prompt injection (Muse)", "f3_injection.txt"),
    ("Part 4.3: blocked link (Muse)", "f3_blocked.txt"),
    ("Part 6: watch.py metrics, run timing and snapshot (Muse)", "p6_metrics_output.txt"),
    ("Part 6: usage reading", "p6_usage.txt"),
]
out = ["DATA-260 HW11 RUN_LOG  (local time; raw files in raw/; Muse text pasted verbatim by the student)", ""]
for title, name in SECTIONS:
    p = RAW / name
    stamp = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    out += [f"################ {title}: raw/{name}  (file written {stamp})", p.read_text(encoding="utf-8", errors="replace").replace("﻿", "").rstrip(), ""]
(HW / "RUN_LOG.txt").write_text("\n".join(out), encoding="utf-8", newline="\n")
print("wrote RUN_LOG.txt,", len(out), "lines")
