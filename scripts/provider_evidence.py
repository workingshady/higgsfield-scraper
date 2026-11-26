"""Count provider / inference-platform fingerprints in stored community job data.

Reads the raw community API envelopes saved by
``python -m higgsfield_scraper scrape community --with-raw-params`` (``runs/*/raw/community_*.json``),
de-duplicates jobs by id, and reports, per ``job_set_type``:

* every distinct URL host found anywhere in ``params`` / ``meta`` / ``result(s)`` / ``job_set_client_meta``
  (the ``prompt`` text is skipped);
* vendor usage/billing fingerprints (OpenAI, Gemini, xAI, DashScope, Kling, BytePlus, MiniMax, ElevenLabs, Topaz);
* inference-platform fingerprints (fal, Replicate, Vertex, Bedrock, Azure, BytePlus/Volcengine, DashScope OSS);
* provider-ish keys (``provider``, ``vendor``, ``backend``, ``use_*`` ...);
* the key set ("shape") of the ``meta.cost`` provider bill.

Output is field names, hosts, counts and truncated id prefixes only: no prompts, usernames or user ids.

Usage::

    python scripts/provider_evidence.py                          # all runs/*/raw/community_*.json
    python scripts/provider_evidence.py --runs runs/2026*_provider-evidence
    python scripts/provider_evidence.py --js samples/higgsfield/js2   # also scan JS chunks
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s\"'<>)]+")
SKIP_KEYS = {"prompt", "negative_prompt", "user_id", "username", "text", "script"}

# Hosts that would prove a third-party inference platform or vendor storage served the file.
PLATFORM_HOSTS = {
    "fal": re.compile(r"(^|\.)fal\.(media|run|ai)$|falserverless", re.I),
    "replicate": re.compile(r"replicate\.(delivery|com)$", re.I),
    "byteplus/volcengine (TOS/ark)": re.compile(r"byteplus|volces\.com|volcengine|bytepluses|ibytedtos|tos-", re.I),
    "alibaba oss/dashscope": re.compile(r"aliyuncs\.com|dashscope|alicdn", re.I),
    "kling": re.compile(r"klingai|kuaishou|kwai", re.I),
    "minimax": re.compile(r"minimax|hailuo", re.I),
    "openai": re.compile(r"openai\.com|oaidalleapi|oaiusercontent", re.I),
    "google api/vertex": re.compile(r"googleapis\.com|googleusercontent", re.I),
    "azure blob": re.compile(r"windows\.net|azure", re.I),
    "aws s3 (direct)": re.compile(r"amazonaws\.com", re.I),
    "together/fireworks/deepinfra/novita/wavespeed/piapi/modal/baseten/runpod": re.compile(
        r"together|fireworks|deepinfra|novita|wavespeed|piapi|modal\.run|baseten|runpod", re.I),
}

PROVIDER_KEY_RE = re.compile(
    r"^(provider|vendor|backend|engine|upstream.*|source|webhook.*|queue.*|endpoint_id|model_version|"
    r"use_[a-z0-9_]+|fal_.*|replicate_.*|req_key|task_id|base_resp|responseId|response_id|request_id|trace_id)$",
    re.I,
)

ID_SHAPES = {
    "openai req_ id": re.compile(r"^req_[0-9a-f]{16,}$"),
    "byteplus cgt- task id": re.compile(r"^cgt-\d{8,}"),
    "kling numeric task id (18-19 digits)": re.compile(r"^\d{18,19}$"),
    "replicate-style id (26 base32)": re.compile(r"^[a-z0-9]{26}$"),
    "64-hex (replicate version hash?)": re.compile(r"^[0-9a-f]{64}$"),
}

TOPAZ_CODES = re.compile(r"^(prob-\d|ahq-\d+|iris-\d|rhea-\d|ghq-\d|thd-\d|slc-\d|slf-\d|slp-[\d.]+|apo-\d|nyx-\d|amq-\d+)$")

USAGE_KEYS = {
    "openai images usage (input_text_tokens/output_image_tokens)": {"input_text_tokens", "output_image_tokens",
                                                                   "input_image_tokens"},
    "openai responses usage (input_tokens_details)": {"input_tokens_details", "output_tokens_details"},
    "gemini usageMetadata (camelCase)": {"usageMetadata", "thoughtsTokenCount", "candidatesTokenCount",
                                         "promptTokenCount"},
    "gemini-style token buckets (thinking_tokens)": {"thinking_tokens"},
    "minimax base_resp": {"base_resp"},
    "elevenlabs character counts": {"character_count", "characters_used", "character_cost"},
    "dashscope usage (output.task_id / usage.video_count)": {"video_count", "task_status"},
}


def walk(obj, path=""):
    """Yield (key_path, key, value) for every leaf; skip free-text/user fields."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in SKIP_KEYS:
                continue
            sub = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                yield (sub, k, None)
                yield from walk(v, sub)
            else:
                yield (sub, k, v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, path + "[]")


def all_keys(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            all_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            all_keys(v, out)


def parse_cost(meta):
    if not isinstance(meta, dict):
        return None
    c = meta.get("cost")
    if isinstance(c, str):
        try:
            c = json.loads(c)
        except ValueError:
            return {"<unparsed string>": True}
    return c if isinstance(c, (dict, list)) else None


def load_items(patterns):
    seen = {}
    files = []
    for p in patterns:
        files += glob.glob(os.path.join(p, "raw", "community_*.json"))
    for f in sorted(files):
        try:
            with open(f, encoding="utf-8") as fh:
                env = json.load(fh)
        except (OSError, ValueError):
            continue
        body = env.get("body", env) if isinstance(env, dict) else {}
        items = body.get("items") if isinstance(body, dict) else None
        for it in items or []:
            if isinstance(it, dict) and it.get("id") and it.get("job_set_type"):
                seen.setdefault(it["id"], it)
    return list(seen.values()), len(files)


def analyse(items):
    per = defaultdict(lambda: {"n": 0, "hosts": Counter(), "fp": Counter(), "shapes": Counter(),
                               "pkeys": Counter(), "id_examples": {}, "scalars": []})
    hosts_total = Counter()
    for it in items:
        t = it["job_set_type"]
        row = per[t]
        row["n"] += 1
        scope = {k: it.get(k) for k in ("params", "meta", "result", "results", "job_set_client_meta")}
        scope["meta_cost"] = parse_cost(it.get("meta"))
        hosts_here, fps, pkeys = set(), set(), set()
        for kpath, key, val in walk(scope):
            if PROVIDER_KEY_RE.match(key or ""):
                pkeys.add(kpath.split(".", 1)[0] + "…" + key)
            if key and key.startswith("use_"):
                fps.add(f"flag {key}={val}")
            if isinstance(val, str):
                for u in URL_RE.findall(val):
                    h = (urlparse(u).hostname or "").lower()
                    if h:
                        hosts_here.add(h)
                for name, rx in ID_SHAPES.items():
                    if rx.match(val):
                        fps.add(name)
                        row["id_examples"].setdefault(name, f"{key}={val[:8]}…")
                if key in ("model", "model_name", "model_id") and TOPAZ_CODES.match(val):
                    fps.add("topaz model code")
        keys = set()
        all_keys(scope, keys)
        cost = scope["meta_cost"]
        raw_cost = (it.get("meta") or {}).get("cost") if isinstance(it.get("meta"), dict) else None
        if cost is None and raw_cost not in (None, ""):
            try:
                val = float(raw_cost)
                fps.add("meta.cost scalar number")
                row["scalars"].append(val)
            except (TypeError, ValueError):
                pass
        if cost is not None:
            ck = set()
            all_keys(cost, ck)
            keys |= ck
            row["shapes"]["{" + ",".join(sorted(ck)) + "}"] += 1
            fps.add("meta.cost present")
            if isinstance(cost, dict) and set(cost) == {"value"}:
                fps.add("meta.cost {value} only (USD/job)")
        for name, ks in USAGE_KEYS.items():
            if keys & ks:
                fps.add(name)
        for h in hosts_here:
            row["hosts"][h] += 1
            hosts_total[h] += 1
            for name, rx in PLATFORM_HOSTS.items():
                if rx.search(h):
                    fps.add(f"PLATFORM HOST: {name}")
        if it.get("trace_id") and it.get("trace_id") != it.get("id"):
            fps.add("trace_id != job id")
        for f in fps:
            row["fp"][f] += 1
        for k in pkeys:
            row["pkeys"][k] += 1
    return per, hosts_total


def scan_js(js_dir):
    terms = ["fal.ai", "fal.run", "fal.media", "@fal-ai", "falserverless", "replicate.com", "replicate.delivery",
             "byteplus", "volcengine", "volces.com", "ark.cn-beijing", "ark.ap-southeast", "dashscope", "aliyuncs",
             "aiplatform.googleapis", "generativelanguage", "vertexai", "bedrock", "azure", "openai.azure",
             "together.ai", "together.xyz", "fireworks.ai", "deepinfra", "novita", "wavespeed", "piapi", "modal.run",
             "baseten", "runpod", "openrouter", "api.openai.com", "api.x.ai", "klingai.com", "minimaxi",
             "api.elevenlabs.io", "topazlabs"]
    files = sorted(glob.glob(os.path.join(js_dir, "*.js")))
    hits = Counter()
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            s = fh.read().lower()
        for t in terms:
            if t in s:
                hits[t] += 1
    return len(files), [(t, hits[t]) for t in terms]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", nargs="*", default=["runs/*"], help="run folder globs (default: runs/*)")
    ap.add_argument("--js", default=None, help="also scan JS chunks in this folder for platform strings")
    ap.add_argument("--min", type=int, default=1, help="only list job types with at least this many jobs")
    a = ap.parse_args(argv)

    dirs = sorted({d for p in a.runs for d in glob.glob(p) if os.path.isdir(d)})
    items, nfiles = load_items(dirs)
    per, hosts_total = analyse(items)
    print(f"# Provider fingerprints\n\n{len(items)} unique jobs, {len(per)} job types, {nfiles} raw envelopes "
          f"from {len(dirs)} run folders.\n")

    print("## URL hosts (all jobs)\n\n| host | jobs |\n|---|---|")
    for h, c in hosts_total.most_common():
        print(f"| `{h}` | {c} |")

    plat = Counter()
    for row in per.values():
        for f, c in row["fp"].items():
            if f.startswith("PLATFORM HOST"):
                plat[f] += c
    print("\n## Third-party platform hosts\n")
    print("\n".join(f"- {k}: {v} jobs" for k, v in plat.items()) or "- none found")

    print("\n## Per job_set_type\n\n| job_set_type | jobs | fingerprints (jobs) | meta.cost shapes | hosts |\n|---|---|---|---|---|")
    for t in sorted(per, key=lambda x: -per[x]["n"]):
        row = per[t]
        if row["n"] < a.min:
            continue
        fp = "; ".join(f"{k} ({v})" for k, v in sorted(row["fp"].items())) or "-"
        sh = "; ".join(f"`{k}` ({v})" for k, v in row["shapes"].most_common(3))
        if row["scalars"]:
            s = row["scalars"]
            sh = (sh + "; " if sh else "") + f"scalar {min(s):g}–{max(s):g} (n={len(s)})"
        sh = sh or "-"
        hs = ", ".join(f"`{h}`" for h, _ in row["hosts"].most_common()) or "-"
        print(f"| `{t}` | {row['n']} | {fp} | {sh} | {hs} |")

    print("\n## Provider-ish keys (where: job count)\n")
    agg = Counter()
    for row in per.values():
        agg.update(row["pkeys"])
    for k, v in agg.most_common():
        print(f"- `{k}`: {v}")

    print("\n## Id-shape examples (truncated)\n")
    for t, row in sorted(per.items()):
        for name, ex in row["id_examples"].items():
            print(f"- `{t}` {name}: `{ex}`")

    if a.js:
        n, hits = scan_js(a.js)
        print(f"\n## JS platform strings ({n} chunks)\n\n| term | chunks |\n|---|---|")
        for t, c in hits:
            print(f"| `{t}` | {c} |")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
