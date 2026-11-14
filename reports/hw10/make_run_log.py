"""Builds reports/hw10/RUN_LOG.txt from the real console output files in raw/ (each section headed with the file's modification time, local time)."""
import datetime
import pathlib

HW = pathlib.Path(__file__).resolve().parent
RAW = HW / "raw"
SECTIONS = [
    ("Part 4.1/4.2: capture of the three required traces", "part4_capture_console.txt"),
    ("Part 2: evaluator on 6 requests (console)", "part2_console.txt"),
    ("Part 2: evaluator bounds tests", "part2_test_evaluator.txt"),
    ("Part 3.1: freezing the 20 evaluation cases (console)", "part3_make_cases_console.txt"),
    ("Part 3.2/3.3: judge vs human labels, three runs (console)", "part3_console.txt"),
    ("Part 4.3: 50 confirmed cache misses, evaluation and 10 cache hits (console)", "part4_latency_console.txt"),
    ("Part 1: dashboard tests (headless Streamlit)", "part1_dashboard_test.txt"),
    ("Part 1: dashboard screenshots (Playwright)", "part1_screenshots_console.txt"),
    ("verify_hw10.py against deliberately broken states", "verify_broken_states.txt"),
]
out = ["DATA-260 HW10 RUN_LOG  (local time; raw files in raw/)", ""]
for title, name in SECTIONS:
    p = RAW / name
    stamp = datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    out += [f"################ {title}: raw/{name}  (file written {stamp})", p.read_text(encoding="utf-8", errors="replace").replace("\ufeff", "").rstrip(), ""]
(HW / "RUN_LOG.txt").write_text("\n".join(out), encoding="utf-8", newline="\n")
print("wrote RUN_LOG.txt,", len(out), "lines")
