"""Generate docs/ENDPOINT_FIELDS.md: every JSON path in each raw API response, with types and an example.

Usage:  python scripts/gen_endpoint_fields.py [RUN_DIR]      (default: latest run)
Re-run after a scrape whenever the API changes, then diff the doc.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from higgsfield_scraper.run.context import latest_run  # noqa: E402

ENDPOINTS = [
    ("plans", "plans__", "GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plans?plan_set_key=…&with_localization=true"),
    ("compare", "compare__", "GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/compare?plan_set_key=…&billing_period=…"),
    ("plan_benefits", "plan_benefits", "GET https://fnf-api-gw.higgsfield.ai/fnf/subscriptions/v2/plan-benefits?locale=en"),
    ("job_costs", "job_costs", "GET https://fnf-api-gw.higgsfield.ai/fnf/job-sets/costs"),
    ("pricing_config", "pricing_config", "GET https://pricing.higgsfield.ai/v2/pricing-config?locale=en[&planVersion=…]"),
]
# parent path suffix -> placeholder for its dynamic keys
DYNAMIC = {"versions": "<version>", "cards": "<billing_period>", "tab_badges": "<tab>", "values": "<plan_type>",
           "billingPeriods": "<billing_period>", "customSections": "<section_id>"}


def walk(node, path: str, acc, examples) -> None:
    if isinstance(node, dict):
        if path:
            acc[path].add("object")
        for k, v in node.items():
            last = path.rsplit(".", 1)[-1]
            key = DYNAMIC.get(last, k)
            if last == "plans" and path.startswith("versions"):
                key = "<plan_type>"
            walk(v, f"{path}.{key}" if path else key, acc, examples)
    elif isinstance(node, list):
        acc[path + "[]"].add("list")
        for x in node:
            walk(x, path + "[]", acc, examples)
    else:
        acc[path].add("null" if node is None else type(node).__name__)
        if node is not None:
            examples.setdefault(path, node)


def main() -> int:
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_run("runs")
    raw = run / "raw"
    lines = ["# Endpoint field reference (auto-generated)", "",
             f"Every JSON path seen in the raw responses of run `{run.name}`, with observed types and one example.",
             "Dynamic object keys are shown as `<placeholder>`; `[]` marks list items. Regenerate with",
             "`python scripts/gen_endpoint_fields.py [RUN_DIR]`. Field meanings: see `ENDPOINTS.md`.", ""]
    for name, prefix, url in ENDPOINTS:
        files = sorted(raw.glob(f"{prefix}*.json"))
        if not files:
            continue
        acc, examples = collections.defaultdict(set), {}
        for f in files:
            body = json.loads(f.read_text(encoding="utf-8"))["body"]
            walk(body, "", acc, examples)
        lines += [f"## `{name}`", "", f"`{url}` — {len(acc)} distinct paths from {len(files)} response(s).", "",
                  "| path | types | example |", "|---|---|---|"]
        for p in sorted(acc):
            ex = json.dumps(examples[p], ensure_ascii=False) if p in examples else ""
            ex = (ex[:57] + "…") if len(ex) > 60 else ex
            ex = ex.replace("|", "\\|")
            lines.append(f"| `{p}` | {'/'.join(sorted(acc[p]))} | {ex} |")
        lines.append("")
    out = Path(__file__).resolve().parents[1] / "docs" / "ENDPOINT_FIELDS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines)} lines) from {run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
