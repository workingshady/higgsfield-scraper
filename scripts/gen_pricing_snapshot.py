"""Render a Markdown pricing snapshot from a pricing run's output/dataset.json.

Usage:
    python scripts/gen_pricing_snapshot.py                      # latest successful pricing run -> stdout
    python scripts/gen_pricing_snapshot.py --run 20261126-092524_pricing-doc
    python scripts/gen_pricing_snapshot.py --write docs/PRICING.md   # replace the block between the markers

The block written into the doc sits between `<!-- BEGIN pricing-snapshot -->` and `<!-- END pricing-snapshot -->`.
No network access; reads only the run folder.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BEGIN = "<!-- BEGIN pricing-snapshot -->"
END = "<!-- END pricing-snapshot -->"


# ------------------------------------------------------------------ run lookup
def find_run(runs_dir: Path, run: Optional[str] = None) -> Path:
    """`--run` (folder or id), else the latest successful pricing run with a dataset (preferring one with plans)."""
    from higgsfield_scraper.pricing_diff import pricing_runs, resolve_run

    if run:
        return resolve_run(run, runs_dir)
    runs = pricing_runs(runs_dir)
    if not runs:
        raise FileNotFoundError(f"no successful pricing run with output/dataset.json in {runs_dir}")
    for d in reversed(runs):
        ds = _load(d)
        if ds.get("plan_sets") and ds.get("models"):
            return d
    return runs[-1]


def _load(run_dir: Path) -> dict:
    return json.loads((run_dir / "output" / "dataset.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ formatting
def _usd(v: Any) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v))
    return f"${d:,.2f}"


def _num(v: Any) -> str:
    if v is None:
        return "—"
    f = float(v)
    return f"{int(f):,}" if f == int(f) else f"{f:g}"


def _pair(p: dict) -> str:
    return f"{_usd(p.get('total'))} ({_usd(p.get('per_month'))}/mo)"


def _discount(d: Optional[dict]) -> str:
    if not d:
        return "—"
    pct = d.get("percent_off")
    pct_s = f"{float(pct):g}%" if pct is not None else "?"
    return f"−{pct_s} `{d.get('duration')}` → {d.get('applies_to')}"


def _dims(dims: dict, component: Optional[str]) -> str:
    parts = [f"{k}={v}" for k, v in (dims or {}).items()]
    if component:
        parts.insert(0, f"[{component}]")
    return " ".join(parts) or "—"


def _cheapest(m: dict) -> Optional[dict]:
    pts = [p for p in m.get("price_points") or [] if p.get("credits") is not None]
    return min(pts, key=lambda p: (p["credits"], json.dumps(p.get("dimensions"), sort_keys=True))) if pts else None


def _plan_key(p: dict) -> tuple:
    order = {"starter": 0, "basic": 0, "plus": 1, "ultra": 2, "max": 3, "team": 4, "scale": 5}
    period = {"monthly": 0, "quarterly": 1, "annual": 2}
    return (p.get("plan_set_key"), order.get(p["plan_type"], 9), period.get(p["billing_period"], 9),
            p.get("credits_per_month") or 0)


# ------------------------------------------------------------------ sections
def render_plans(ds: dict) -> list[str]:
    out = []
    for ps in ds.get("plan_sets") or []:
        plans = sorted(ps.get("plans") or [], key=_plan_key)
        out += [
            f"#### Plans — plan set `{ps['plan_set_key']}` (country by IP: {ps.get('country_code') or '?'}, "
            f"special_offer: `{json.dumps(ps.get('special_offer'))}`)",
            "",
            "Totals are for the whole billing period; `/mo` is per month. Business plans are **per seat** "
            "(minimum seats shown).",
            "",
            "| Plan | Billing | Credits/mo | Credits/period | Seats | Before offer | After offer | Renewal "
            "| Discount → applies to | $/credit before / after / renewal |",
            "|---|---|---:|---:|---:|---|---|---|---|---|",
        ]
        for p in plans:
            pr, ppc = p["pricing"], p["price_per_credit"]
            out.append(
                f"| {p['name']} | {p['billing_period']} | {_num(p['credits_per_month'])} | "
                f"{_num(p['credits_per_period'])} | {p.get('seats') or '—'} | {_pair(pr['before_offer'])} | "
                f"**{_pair(pr['after_offer'])}** | {_pair(pr['renewal'])} | {_discount(p.get('discount'))} | "
                f"{ppc.get('before_offer') or '—'} / {ppc.get('after_offer') or '—'} / {ppc.get('renewal') or '—'} |")
        out.append("")
    return out


def render_benefits(ds: dict) -> list[str]:
    names = {m["model_id"]: m.get("display_name") or m["model_id"] for m in ds.get("models") or []}

    def nm(mid: str) -> str:
        if mid.startswith("label:"):
            return f"{mid[6:]} (campaign)"
        return f"{names.get(mid, mid)} (`{mid}`)"

    out = ["#### Unlimited models and free gens per plan", "",
           "| Plan | Billing | Unlimited models | Free gens (count, max res) |", "|---|---|---|---|"]
    seen = set()
    for ps in ds.get("plan_sets") or []:
        for p in sorted(ps.get("plans") or [], key=_plan_key):
            key = (p["plan_type"], p["billing_period"])
            if key in seen:            # Ultra tiers share one benefit card
                continue
            seen.add(key)
            unl = ", ".join(nm(m) for m in p.get("unlimited_model_ids") or []) or "—"
            fg = ", ".join(
                f"{nm(g['model_id'])} ×{_num(g.get('count'))}" + (f" ≤{g['max_resolution']}" if g.get("max_resolution") else "")
                for g in p.get("free_gens") or []) or "—"
            out.append(f"| {p['name']} | {p['billing_period']} | {unl} | {fg} |")
    out.append("")
    return out


def render_models(ds: dict) -> list[str]:
    ref = (ds.get("meta") or {}).get("usd_reference") or {}
    rate = ref.get("usd_per_credit")
    out = [
        "#### Model credit summary",
        "",
        f"≈USD = credits of the cheapest option (for per-second / per-minute / per-character units: the example "
        f"quantity shown) × the `{ref.get('plan_type')}:{ref.get('billing_period')}` after-offer rate "
        f"(**${rate}/credit**, plan set `{ref.get('plan_set_key')}`). Models with no `/job-sets/costs` entry come only "
        f"from plan benefits.",
        "",
        "| Model | id | Family | Category | Unit (cheapest) | Min cr | Max cr | Cheapest option | Example | ≈USD |",
        "|---|---|---|---|---|---:|---:|---|---|---:|",
    ]
    models = sorted(ds.get("models") or [], key=lambda m: (m.get("category") or "", m.get("family") or "",
                                                         m["model_id"]))
    for m in models:
        c = _cheapest(m)
        if c is None:
            out.append(f"| {m.get('display_name')} | `{m['model_id']}` | {m.get('family')} | {m.get('category')} "
                       f"| no cost data | — | — | — | — | — |")
            continue
        ex = c.get("example") or {}
        ex_s = ", ".join(f"{k}={_num(v)}" for k, v in ex.items()) if ex else "—"
        disc = f" (was {_num(c['original_credits'])})" if c.get("is_discounted") else ""
        usd = c.get("usd_estimate")
        out.append(
            f"| {m.get('display_name')} | `{m['model_id']}` | {m.get('family')} | {m.get('category')} | {c['unit']} | "
            f"{_num(m.get('min_credits'))}{disc} | {_num(m.get('max_credits'))} | {_dims(c.get('dimensions'), c.get('component'))} | "
            f"{ex_s} | {'—' if usd is None else f'${usd:.4f}'} |")
    out.append("")
    return out


def render(ds: dict, run_id: Optional[str] = None) -> str:
    meta = ds.get("meta") or {}
    run_id = run_id or meta.get("run_id")
    c = meta.get("counts") or {}
    head = [
        f"_Generated by `python scripts/gen_pricing_snapshot.py --write docs/PRICING.md` from run "
        f"`{run_id}`, scraped {meta.get('scraped_at')} (country by IP: {meta.get('country_code')}, plan sets: "
        f"{', '.join(meta.get('plan_set_keys') or [])}). `/job-sets/costs` version "
        f"`{(meta.get('costs_version') or '')[:12]}…`, marketing config {meta.get('marketing_latest_version')}. "
        f"Counts: {c.get('plans')} plans, {c.get('models')} models, {c.get('price_points')} price points, "
        f"{c.get('benefit_cards')} benefit cards._",
        "",
    ]
    return "\n".join(head + render_plans(ds) + render_benefits(ds) + render_models(ds)).rstrip() + "\n"


def insert(doc: str, block: str) -> str:
    if BEGIN not in doc or END not in doc:
        raise ValueError(f"markers {BEGIN!r} / {END!r} not found")
    pre, rest = doc.split(BEGIN, 1)
    _, post = rest.split(END, 1)
    return f"{pre}{BEGIN}\n{block}{END}{post}"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="run folder or run id (default: latest successful pricing run)")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--write", metavar="DOC.md", help="replace the snapshot block in this Markdown file")
    a = ap.parse_args(argv)
    run_dir = find_run(Path(a.runs_dir), a.run)
    block = render(_load(run_dir), run_dir.name)
    if a.write:
        p = Path(a.write)
        p.write_text(insert(p.read_text(encoding="utf-8"), block), encoding="utf-8")
        print(f"wrote snapshot of {run_dir.name} into {p}", file=sys.stderr)
    else:
        sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
