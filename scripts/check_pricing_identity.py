"""Guard against corrupting the pricing output: re-parse a reference run offline and compare with a baseline.

Usage:
    python scripts/check_pricing_identity.py                        # defaults below, runs normalize itself
    python scripts/check_pricing_identity.py --new runs/<id>/output # compare an existing output folder

Run ids, timestamps and `scraped_at` lines are masked; everything else must be byte-identical.
Exit 0 = identical, 1 = differences (listed), 2 = missing folders.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SOURCE = "runs/20261125-112609_everything-full-csv"
# v2 (2026-11-26): same data as v1 (runs/20261125-122450_pricing-baseline) except meta.label, which v1 had wrong
# ("Soul V2 & Cinema"; fixed in assemble.py). Only that one line per file differed.
BASELINE = "runs/20261126-094534_pricing-baseline-v2/output"
CHECK_LABEL = "pricing-identity-check"
NORMALIZE_ARGS = ["--sections", "all", "--plan-sets", "all", "--marketing-versions", "all",
                  "--include-raw-cost", "--include-hidden-plans"]

RID = re.compile(rb"\d{8}-\d{6}_[a-z0-9-]+")
TS = re.compile(rb"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?")


def norm(data: bytes, label: str = "") -> bytes:
    """Mask run ids, timestamps and this run's own --label (it legitimately differs between runs)."""
    data = TS.sub(b"TS", RID.sub(b"RID", data))
    if label:
        data = data.replace(label.encode(), b"LABEL")
    return b"\n".join(line for line in data.split(b"\n") if b"scraped_at" not in line)


def run_label(output: Path) -> str:
    """The run label = folder name after the timestamp (<yyyymmdd-HHMMSS>_<label>)."""
    m = re.match(r"\d{8}-\d{6}_(.+?)(-\d+)?$", output.parent.name)
    return m.group(1) if m else ""


def compare(new: Path, base: Path) -> tuple[list[str], list[str], list[str], int]:
    fa = {p.relative_to(new).as_posix() for p in new.rglob("*") if p.is_file()}
    fb = {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}
    ln, lb = run_label(new), run_label(base)
    diff = [f for f in sorted(fa & fb) if norm((new / f).read_bytes(), ln) != norm((base / f).read_bytes(), lb)]
    return sorted(fa - fb), sorted(fb - fa), diff, len(fa & fb) - len(diff)


def run_normalize(runs_dir: str) -> Path:
    before = {p.name for p in Path(runs_dir).iterdir()}
    subprocess.run([sys.executable, "-m", "higgsfield_scraper", "normalize", "--run", SOURCE, *NORMALIZE_ARGS,
                    "--runs-dir", runs_dir, "--label", CHECK_LABEL, "-q"], check=True)
    new = sorted(p for p in Path(runs_dir).iterdir() if p.name not in before and p.is_dir())
    return new[-1] / "output"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--new", help="output folder to check (default: run normalize on the reference run)")
    ap.add_argument("--baseline", default=BASELINE)
    ap.add_argument("--runs-dir", default="runs")
    a = ap.parse_args()
    base = Path(a.baseline)
    if not base.is_dir() or (not a.new and not Path(SOURCE).is_dir()):
        print(f"missing baseline {base} or source {SOURCE}")
        return 2
    new = Path(a.new) if a.new else run_normalize(a.runs_dir)
    only_new, only_base, diff, same = compare(new, base)
    print(f"checked {new}")
    for f in only_new:
        print("ONLY IN NEW:", f)
    for f in only_base:
        print("MISSING:", f)
    for f in diff:
        print("DIFF:", f)
    print(f"identical={same} different={len(diff)} missing={len(only_base)} extra={len(only_new)}")
    return 0 if not (diff or only_new or only_base) else 1


if __name__ == "__main__":
    raise SystemExit(main())
