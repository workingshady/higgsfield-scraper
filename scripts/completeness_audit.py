"""Completeness audit: does every generation-like record keep everything the source API provides?

Read-only. Works on finished run folders (`raw/` envelopes + `output/json/`), never sends a request.

    python scripts/completeness_audit.py runs/<a> runs/<b> ...            # Markdown tables to stdout
    python scripts/completeness_audit.py "runs/*nested*" --md out.md --json out.json
    python scripts/completeness_audit.py runs/<new...> --baseline runs/<old...>   # + raw paths new vs old

Method (generic, no per-scraper mapping needed):

1. Output pass: every record of every `output/json/<kind>.json` (streamed element by element, so a 54 MB
   `assets.json` never sits in memory as a tree) is walked leaf by leaf. Distinctive values (long strings, URLs,
   timestamps, big numbers) go into a run-wide hash set; low-entropy values (bools, small ints, short strings) are
   kept per record as (key, value) pairs, indexed by every id in the record. JSON strings are exploded.
2. Raw pass: every `raw/*.json` body is split into records (the lists of objects nearest to the root, else the body),
   each raw leaf is "kept" if its canonical value is found in the output (distinctive: anywhere in the run;
   low-entropy: in the joined output record under the same / a similar key). The rest is "dropped".
3. Feature coverage (prompt, media variants, inputs, model, settings, cost, engagement, lineage, ...) is computed by
   key-name heuristics on both the raw record and its joined output record, so "missing in source" and
   "missing in our output" are separated.

Caveats: value matching can over-report "kept" for very common values and under-report for values the parser
transforms (unit conversions, Markdown); HTML/text bodies (site landing pages, effect pages) are not leaf-audited.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Iterator

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?")
NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
USER_RE = re.compile(r"user_[A-Za-z0-9]{20,}")
DYN_KEY_RE = re.compile(r"^([0-9a-f]{8}-[0-9a-f-]{27}|\d+|[0-9a-f]{16,}|user_[A-Za-z0-9]{20,})$")
CAMEL_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")

VIDEO_EXT = (".mp4", ".mov", ".webm", ".m3u8", ".mkv", ".m4v")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".heic", ".svg")
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus")
D3_EXT = (".glb", ".gltf", ".obj", ".fbx", ".usdz", ".ply", ".splat", ".zip", ".pdf")
MEDIA_HOST = ("cloudfront.net", "cdn.", "storage.", "r2.", "s3.", "amazonaws", "mux.", "stream", "cdn-", "media.")

SKIP_OUTPUT = {"meta", "summary", "nested_summary", "pages", "stats", "extra_stats", "gallery_stats"}
PERSONAL_TOK = {"username", "user_name", "avatar", "avatar_url", "full_name", "first_name", "last_name", "email",
                "headline", "bio", "instagram_handle", "twitter_handle", "youtube_handle", "tiktok_handle",
                "display_name", "handle", "profile_image", "image_url_profile", "phone", "nickname", "socials"}
PERSON_CTX = {"profile", "user", "author", "creator", "owner", "judge", "judges", "commenter", "members"}
MODEL_KEYS = ("job_set_type", "job_type", "model_id", "model_slug", "model_key", "model", "model_name", "codename",
              "generator", "engine", "ai_model")
INPUT_TOK = ("input", "reference", "ref_", "_ref", "medias", "start_", "end_", "first_frame", "last_frame",
             "element", "character", "mask", "init_", "source_image", "source_video", "driving", "face_", "audio_url",
             "voice_url", "image_url", "video_url", "frames", "keyframe", "subject")
LINEAGE_KEYS = ("parent_id", "job_set_parent_id", "parent_job_id", "parent_publication_id", "remix_of", "remixed_from",
                "original_job_id", "original_id", "source_job_id", "based_on", "forked_from", "parent",
                "parent_job_set_id", "root_id", "remix_id", "source_publication_id", "reference_job_id")
ENG_TOK = ("like", "view", "comment", "share", "favorite", "favourite", "vote", "play", "download", "remix",
           "repost", "save", "reaction", "follower", "uses", "usage_count", "runs")
COST_TOK = ("credit", "cost", "price", "usd", "amount", "fee")
TEMPLATE_TOK = ("preset", "template", "motion_id", "style_id", "effect", "chain", "workflow", "app_id", "style",
                "motion", "lora", "camera_model", "camera_lens", "voice_id", "avatar_id", "sound_id")
SETTING_ROOTS = ("params", "raw_params", "settings", "params_extra", "options", "config", "generation_params",
                 "input_params", "arguments")

VALUABLE_TOK = ("prompt", "url", "media", "video", "image", "audio", "thumbnail", "poster", "preview", "input",
                "reference", "frame", "element", "character", "model", "job_set", "version", "codename", "params",
                "setting", "resolution", "duration", "aspect", "quality", "seed", "batch", "mode", "motion",
                "preset", "template", "style", "credit", "cost", "price", "like", "view", "comment", "share",
                "remix", "parent", "status", "created", "published", "width", "height", "fps", "voice", "sound",
                "lyrics", "negative", "enhance", "result", "output", "cfg", "steps", "strength", "camera", "lens",
                "genre", "language", "tags", "category", "title", "description", "caption", "count")
INTENTIONAL_TOK = ("blur", "blurhash", "placeholder", "is_liked_by_user", "is_favourite", "is_viewed",
                   "is_liked", "is_followed", "liked_by", "has_unresolved", "can_bypass", "_by_user",
                   "color", "icon", "sort", "order", "position", "z_index", "rotation", "trace_id",
                   "cluster_hash", "request_id", "workspace_id", "cursor", "has_more", "next", "total")


# ------------------------------------------------------------------ helpers
def h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8", "replace"), digest_size=8).digest(), "big")


def nkey(k: Any) -> str:
    k = str(k)
    if DYN_KEY_RE.match(k):
        return "{id}"
    return CAMEL_RE.sub(r"_\1", k).lower()


def is_time_key(k: str) -> bool:
    return k.endswith("_at") or k in ("created", "updated", "published", "date", "timestamp", "time") or \
        k.endswith("_time") or k.endswith("_date")


def ts_canon(v: float) -> str | None:
    if 1e12 <= v < 2e13:
        v = v / 1000
    if 9e8 <= v < 4e9:
        return "t:" + dt.datetime.fromtimestamp(int(v), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return None


def canon(v: Any, key: str = "") -> tuple[str, bool] | None:
    """(canonical string, distinctive?) or None for null/empty."""
    if v is None:
        return None
    if isinstance(v, bool):
        return "b:" + str(v), False
    if isinstance(v, (int, float)):
        if is_time_key(key):
            t = ts_canon(float(v))
            if t:
                return t, True
        f = float(v)
        return "n:" + format(round(f, 6), ".10g"), abs(f) >= 100000 or (f != int(f) and len(str(v)) > 6)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if ISO_RE.match(s):
            try:
                d = dt.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")[:32])
                if d.tzinfo is None:
                    d = d.replace(tzinfo=dt.timezone.utc)
                return "t:" + d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), True
            except ValueError:
                pass
        if NUM_RE.match(s) and len(s) < 20:
            f = float(s)
            return "n:" + format(round(f, 6), ".10g"), abs(f) >= 100000 or ("." in s and len(s) > 6)
        return "s:" + s, len(s) >= 8 or " " in s
    return None


def url_variants(s: str) -> list[str]:
    out = [s]
    if s.startswith("s:http"):
        base = s.split("?", 1)[0].split("#", 1)[0]
        if base != s:
            out.append(base)
    return out


def maybe_json(v: Any) -> Any:
    if isinstance(v, str) and len(v) > 1 and v.lstrip()[:1] in "{[":
        try:
            return json.loads(v)
        except ValueError:
            return None
    return None


def leaves(o: Any, path: tuple = (), parent: dict | None = None, depth: int = 0) -> Iterator[tuple[tuple, Any, dict | None]]:
    """(path tuple of normalized keys, value, parent dict). Lists add '[]'. JSON strings are exploded with '{json}'."""
    if depth > 40:
        return
    if isinstance(o, dict):
        for k, v in o.items():
            yield from leaves(v, path + (nkey(k),), o, depth + 1)
    elif isinstance(o, list):
        for v in o:
            yield from leaves(v, path + ("[]",), parent, depth + 1)
    else:
        yield path, o, parent
        j = maybe_json(o)
        if j is not None:
            yield from leaves(j, path + ("{json}",), None, depth + 1)


def last_key(path: tuple) -> str:
    for p in reversed(path):
        if p not in ("[]", "{json}", "{id}"):
            return p
    return ""


def tokens(k: str) -> set[str]:
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in k.split("_")
            if len(t) >= 3 and t not in ("url", "count", "the", "has", "ids", "num", "total")}


def keysim(a: str, b: str) -> bool:
    if a == b or a in b or b in a:
        return True
    ta, tb = tokens(a), tokens(b)
    return bool(ta & tb)


def stream_json_list(path: str) -> Iterator[Any]:
    """Yield top-level list elements one by one (raw_decode over the text: no full tree in memory)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    dec = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n and text[i] in " \t\r\n﻿":
        i += 1
    if i >= n:
        return
    if text[i] != "[":
        obj = dec.raw_decode(text, i)[0]
        del text
        if isinstance(obj, dict):
            lists = [v for v in obj.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
            if len(lists) == 1 and len(obj) <= 3:
                yield from lists[0]
            else:
                yield obj
        elif isinstance(obj, list):
            yield from obj
        return
    i += 1
    while True:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            return
        obj, i = dec.raw_decode(text, i)
        yield obj


def redact(s: Any, n: int = 70) -> str:
    s = USER_RE.sub("user_<redacted>", str(s)).replace("\n", " ").replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "..."


# ------------------------------------------------------------------ features
def media_kind_of(url: str, parent: dict | None) -> str:
    u = url.lower().split("?", 1)[0]
    t = str((parent or {}).get("type") or (parent or {}).get("media_type") or (parent or {}).get("mime_type") or "").lower()
    if u.endswith(VIDEO_EXT) or "video" in t:
        return "video"
    if u.endswith(AUDIO_EXT) or "audio" in t:
        return "audio"
    if u.endswith(D3_EXT) or "model3d" in t or "3d" == t:
        return "3d/file"
    if u.endswith(IMAGE_EXT) or "image" in t:
        return "image"
    return "other"


def is_media_url(v: Any, path: tuple) -> bool:
    if not isinstance(v, str) or not v.startswith("http"):
        return False
    lk = last_key(path)
    if lk in ("source_url", "page_url", "href", "link", "canonical_url", "share_url", "permalink", "website",
              "url_page", "og_url", "api_url", "endpoint", "docs_url"):
        return False
    u = v.lower().split("?", 1)[0]
    if u.endswith(VIDEO_EXT + IMAGE_EXT + AUDIO_EXT + D3_EXT):
        return True
    return any(x in u for x in MEDIA_HOST) and ("url" in lk or "src" in lk or lk in ("video", "image", "audio", "hls", "mp4", "poster", "thumbnail"))


def is_person_path(path: tuple) -> bool:
    return any(p in PERSON_CTX or p in PERSONAL_TOK or "avatar" in p or "badge" in p for p in path)


INPUT_SEG = ("input", "reference", "ref_", "start_", "end_", "first_frame", "last_frame", "element", "character",
             "mask", "init_", "source_image", "source_video", "driving", "keyframe", "control_")


def is_input_path(path: tuple) -> bool:
    for p in path:
        if p in SETTING_ROOTS or p == "inputs":
            return True
        if p.startswith(INPUT_SEG) or p.endswith(("_input", "_inputs", "_reference", "_references", "_ref", "_refs")):
            return True
    return False


def variant_of(path: tuple, parent: dict | None, url: str) -> str:
    toks = " ".join(path) + " " + str((parent or {}).get("name") or (parent or {}).get("variant") or "")
    u = url.lower().split("?", 1)[0]
    if "blur" in toks:
        return "blur"
    if "hls" in toks or u.endswith(".m3u8"):
        return "hls"
    if "h264" in toks:
        return "h264"
    if any(t in toks for t in ("thumb", "poster", "preview", "cover", "still", "snapshot", "first_frame_url")):
        return "thumb"
    if re.search(r"\bmin\b|_min\b|\bmin_", toks):
        return "min"
    if re.search(r"\braw\b|_raw\b|\braw_", toks):
        return "raw"
    if "webp" in toks or "gif" in toks:
        return "anim"
    return "main"


def feats(rec: Any) -> dict:
    f = {"prompt": False, "neg": False, "enh": False, "nprompts": 0, "variants": set(), "mkinds": set(),
         "inputs": 0, "roles": set(), "model": None, "settings": set(), "cost": False, "eng": set(),
         "lineage": False, "ts": False, "status": False, "template": False, "users": set(), "out_urls": 0,
         "urlv": {}, "allurls": set(), "inurls": set()}
    prompts = set()
    for path, v, parent in leaves(rec):
        if v is None or v == "" or v == []:
            continue
        lk = last_key(path)
        pstr = "/".join(path)
        if isinstance(v, str) and v.startswith("user_") and len(v) > 20 and USER_RE.fullmatch(v):
            f["users"].add(v)
        if lk in ("author_key", "creator_key", "owner_key", "user_key"):
            f["users"].add("key:" + str(v))
        if is_person_path(path):
            continue
        if isinstance(v, str) and "prompt" in lk and not any(x in lk for x in ("language", "_id", "type", "mode", "enhance_prompt", "count", "lang")) and len(v.strip()) >= 3 and not v.startswith("http"):
            if "negative" in lk:
                f["neg"] = True
            elif any(x in lk for x in ("enhanced", "expanded", "improved", "rewritten", "refined", "final")):
                f["enh"] = True
            else:
                f["prompt"] = True
                prompts.add(v.strip()[:200])
        if is_media_url(v, path):
            hu = h(v.split("?", 1)[0])
            f["allurls"].add(hu)
            if is_input_path(path):
                f["inurls"].add(hu)
                f["inputs"] += 1
                role = (parent or {}).get("role") if isinstance(parent, dict) else None
                f["roles"].add(str(role) if role else next((p for p in reversed(path) if p not in ("[]", "url", "data", "{id}", "{json}", "src")), "?"))
            else:
                f["out_urls"] += 1
                var = variant_of(path, parent, v)
                f["variants"].add(var)
                f["urlv"].setdefault(hu, var)
                f["mkinds"].add(media_kind_of(v, parent))
        if f["model"] is None and lk in MODEL_KEYS and isinstance(v, str) and not v.startswith("http"):
            f["model"] = v
        if any(p in SETTING_ROOTS for p in path) and "prompt" not in lk and not is_media_url(v, path):
            # settings = distinct leaf keys under a params-like root (raw blob or normalized)
            f["settings"].add(lk)
        if any(t in lk for t in COST_TOK) and isinstance(v, (int, float, str)) and not isinstance(v, bool) and \
                (isinstance(v, (int, float)) or NUM_RE.match(str(v).strip() or "x")) and "currency" not in lk:
            f["cost"] = True
        if any(("cost" in p or "usage" in p or "price" in p or "credit" in p) for p in path if p not in ("[]", "{json}")) \
                and isinstance(v, (int, float, str)) and not isinstance(v, bool) and NUM_RE.match(str(v).strip() or "x"):
            f["cost"] = True
        if isinstance(v, (int, float)) and not isinstance(v, bool) and any(t in lk for t in ENG_TOK) and "by_user" not in lk:
            f["eng"].add(next(t for t in ENG_TOK if t in lk))
        if lk in LINEAGE_KEYS or lk.startswith("remix") or lk.startswith("parent_"):
            f["lineage"] = True
        if is_time_key(lk):
            f["ts"] = True
        if lk in ("status", "state", "job_status"):
            f["status"] = True
        if any(t in lk for t in TEMPLATE_TOK) and not isinstance(v, bool):
            f["template"] = True
    f["nprompts"] = len(prompts)
    return f


def primary_kind(f: dict) -> str:
    for k in ("video", "audio", "3d/file", "image", "other"):
        if k in f["mkinds"]:
            return k
    return "none (inputs/prompt only)"


AREAS = (  # (regex on "scraper/endpoint", area) - first match wins
    (r"comments", "comments"),
    (r"community_(trending|approved|top|model|detail)", "community generations (feeds)"),
    (r"community_shots", "community shots"), (r"community_posts", "community posts"),
    (r"community_feed", "community feed"), (r"community_(explore|job_showcase|collection|music)", "community extras"),
    (r"community_(creators|talents)", "creators"),
    (r"contest|submission|entries", "contests"),
    (r"projects_(folder|brief|publication_detail|related|stats)", "project nested (folders/assets)"),
    (r"projects_|series|episode", "projects / series"),
    (r"catalog_(viral|chain)", "templates: viral/chain presets"), (r"catalog_.*motion", "templates: motions"),
    (r"catalog_", "templates: other presets"),
    (r"intone", "showcase intone"), (r"faceless", "showcase faceless"),
    (r"explore", "showcase explore (trends)"), (r"effect", "showcase effects (viral)"),
    (r"reels", "showcase reels"), (r"videoshop", "showcase editing room"), (r"property", "showcase property studio"),
    (r"seedance_presets|motion_control", "showcase seedance/motion presets"),
    (r"cinema_controls", "showcase cinema controls"), (r"canvas", "showcase canvas"), (r"api_", "showcase api models"),
    (r"app", "site apps"), (r"mcp", "site mcp"), (r"room", "site rooms"), (r"^site/", "site pages"),
    (r"^blog/", "blog / help (text)"), (r"community_viral_presets", "templates: viral/chain presets"),
    (r"account", "account jobs"), (r".", "other"),
)


def area_of(scraper: str, ep: str) -> str:
    s = f"{scraper}/{ep}"
    return next(a for rx, a in AREAS if re.search(rx, s))


def union_feats(fs: list[dict]) -> dict:
    """Features of the raw record's output = union over every output record that carries its id
    (the record itself plus its split-out children, e.g. explore item -> explore variants)."""
    if len(fs) == 1:
        return fs[0]
    u = {k: (set() if isinstance(v, set) else ({} if isinstance(v, dict) else v)) for k, v in fs[0].items()}
    for f in fs:
        for k, v in f.items():
            if isinstance(v, set):
                u[k] |= v
            elif isinstance(v, dict):
                u[k].update(v)
            elif isinstance(v, bool):
                u[k] = u[k] or v
            elif isinstance(v, int):
                u[k] = max(u[k], v)
            elif u[k] is None:
                u[k] = v
    return u


def gen_like(f: dict) -> bool:
    return f["prompt"] or f["out_urls"] > 0 or f["inputs"] > 0


TECH_KEYS = {"mime_type", "media_type", "content_type", "size_bytes", "compressed_size_bytes", "audio_streams",
             "object_fit", "_tag", "bucket_name", "object_key", "@type", "@context", "type", "status", "kind",
             "format", "encoding", "codec", "etag", "checksum", "md5", "storage_key"}


def classify(path: str) -> str:
    p = path.lower()
    lk = p.rsplit(".", 1)[-1]
    segs = p.split(".")
    if any(t in segs for t in PERSONAL_TOK) or "avatar" in p or any(c in segs for c in PERSON_CTX) or "badge" in p             or lk in ("user_id", "user_ids", "author_user_ids", "owner_username", "owner_user_id", "workspace_id",
                      "author_handle", "user_key") or (segs and segs[-1] == "[]" and "user_ids" in p):
        return "intentional (personal)"
    if any(t in lk for t in INTENTIONAL_TOK):
        return "intentional (ui/internal)"
    if lk in TECH_KEYS or lk.startswith("_") or "placeholder" in p:
        return "technical metadata"
    if any(t in lk or t in p for t in VALUABLE_TOK):
        return "valuable"
    return "unknown"


# ------------------------------------------------------------------ run audit
def raw_records(body: Any) -> list[tuple[str, dict]]:
    """[(list path, record)] = objects of the lists nearest to the root; else the body itself."""
    out: list[tuple[str, dict]] = []

    def visit(o: Any, path: str, depth: int) -> None:
        if depth > 4 or not isinstance(o, dict):
            return
        if depth > 0 and is_record(o):
            out.append((path, o))
            return
        for k, v in o.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:5]):
                for x in v:
                    if isinstance(x, dict):
                        out.append((f"{path}.{nkey(k)}[]", x))
            elif isinstance(v, dict):
                visit(v, f"{path}.{nkey(k)}", depth + 1)

    if isinstance(body, list):
        return [(".[]", x) for x in body if isinstance(x, dict)]
    if isinstance(body, dict) and is_record(body):
        return [("", body)]
    visit(body, "", 0)
    if not out and isinstance(body, dict):
        out.append(("", body))
    return out


RECORD_KEYS = ("job_set_type", "job_set_id", "params", "results", "prompt", "publication", "job", "slug")


def is_record(o: dict) -> bool:
    """A dict that is itself one entity (detail bodies), not a page wrapper around lists."""
    return isinstance(o, dict) and ("id" in o or "uuid" in o) and any(k in o for k in RECORD_KEYS + ("title", "name", "type"))


def rec_ids(rec: dict) -> list[str]:
    ids = []
    for k in ("id", "uuid", "job_id", "publication_id", "slug"):
        v = rec.get(k)
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            ids.append(str(v))
    for k, v in rec.items():
        if isinstance(v, dict):
            for kk in ("id", "uuid"):
                if isinstance(v.get(kk), (str, int)) and not isinstance(v.get(kk), bool):
                    ids.append(str(v[kk]))
    for k, v in rec.items():
        if isinstance(v, str) and nkey(k).endswith("_id") and UUID_RE.match(v):
            ids.append(v)
    return ids[:6]


def primary_ids(rec: Any) -> dict[str, int]:
    """Own ids of an output record -> rank: the first top-level `id` / `*_id` scalars in schema order
    (schemas list the entity's own id first, references to parents later)."""
    own: dict[str, int] = {}
    if not isinstance(rec, dict):
        return own
    for k, v in rec.items():
        if (k == "id" or k.endswith("_id")) and isinstance(v, (str, int)) and not isinstance(v, bool):
            own.setdefault(str(v), len(own))
            if len(own) >= 3:
                break
    return own


def out_ids(rec: Any) -> set[str]:
    ids = set()
    for path, v, _ in leaves(rec):
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            lk = last_key(path)
            s = str(v)
            if UUID_RE.match(s) or lk == "id" or lk.endswith("_id") or lk in ("slug", "uuid"):
                ids.add(s)
    return ids


def audit_run(run: str, log=print) -> dict:
    man = {}
    try:
        with open(os.path.join(run, "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        pass
    scraper = man.get("scraper") or "pricing"
    raw_files = sorted(glob.glob(os.path.join(run, "raw", "*.json")))
    out_files = sorted(glob.glob(os.path.join(run, "output", "json", "*.json")))

    # phase 0: ids of raw records (to keep per-record pair maps only for joinable output records)
    need: set[str] = set()
    for rf in raw_files:
        body = _raw_body(rf)
        for _, r in raw_records(body):
            need.update(rec_ids(r))
        del body

    # phase 1: output index + output-side coverage
    H: set[int] = set()          # distinctive canonical values
    G: set[int] = set()          # (key, low value) pairs, run-wide
    slots: dict[str, list[int]] = defaultdict(list)
    slot_pairs: list[set[int]] = []
    slot_vals: list[dict[int, tuple]] = []
    slot_feats: list[dict] = []
    slot_kind: list[str] = []
    out_cov: dict[tuple, Counter] = defaultdict(Counter)
    out_users: set[str] = set()
    for of in out_files:
        kind = os.path.splitext(os.path.basename(of))[0]
        if kind in SKIP_OUTPUT:
            continue
        try:
            it = stream_json_list(of)
            for rec in it:
                pairs: set[int] = set()
                vals: dict[int, set] = defaultdict(set)
                for path, v, _ in leaves(rec):
                    lk = last_key(path)
                    c = canon(v, lk)
                    if c is None:
                        continue
                    cs, dist = c
                    if dist:
                        for x in url_variants(cs):
                            H.add(h(x))
                    else:
                        hp = h(lk + "\x00" + cs)
                        pairs.add(hp)
                        G.add(hp)
                        vals[h(cs)].add(lk)
                ids = out_ids(rec) & need if need else set()
                f = feats(rec)
                if ids:
                    idx = len(slot_pairs)
                    slot_pairs.append(pairs)
                    slot_vals.append({k: tuple(v) for k, v in vals.items()})
                    slot_feats.append(f)
                    slot_kind.append(kind)
                    own = primary_ids(rec)
                    for i in ids:
                        rank = own.get(i, 99)             # the record's own id ranks first and is never capped
                        if rank < 99 or len(slots[i]) < 40:
                            slots[i].append((rank, idx))
                out_users.update(f["users"])
                if gen_like(f):
                    _add_cov(out_cov[(kind, f["model"] or "(none)")], f, None)
        except (ValueError, OSError) as e:
            log(f"  ! {of}: {e}", file=sys.stderr)

    # phase 1b: per endpoint, do raw ids join at all? (if yes, an unjoined record was simply not emitted)
    ep_joins: Counter = Counter()
    for rf in raw_files:
        env = _raw_env(rf)
        if env is None:
            continue
        ep = (env.get("meta") or {}).get("endpoint") or os.path.basename(rf).split("__", 1)[0]
        body = env.get("body")
        body = maybe_json(body) if isinstance(body, str) else body
        for _, rec in raw_records(body):
            if any(i in slots for i in rec_ids(rec)):
                ep_joins[ep] += 1
        del env, body

    # phase 2: raw leaves -> kept / dropped, raw-side coverage, missing-in-output
    paths: dict[tuple, dict] = {}
    raw_cov: dict[tuple, Counter] = defaultdict(Counter)
    users: list[tuple[str, str, set]] = []
    nonjson = Counter()
    not_emitted = Counter()
    raw_n = Counter()
    raw_users: set[str] = set()
    for rf in raw_files:
        env = _raw_env(rf)
        if env is None:
            continue
        ep = (env.get("meta") or {}).get("endpoint") or os.path.basename(rf).split("__", 1)[0]
        body = env.get("body")
        if isinstance(body, str):
            j = maybe_json(body)
            if j is None:
                nonjson[ep] += 1
                continue
            body = j
        del env
        for lpath, rec in raw_records(body):
            raw_n[ep] += 1
            ids = rec_ids(rec)
            ranked: list[tuple[int, int]] = []
            for i in ids:
                ranked.extend(slots.get(i, []))
            # output records that carry the raw id as their own id (the entity itself and split-out children,
            # e.g. explore variants) win over records that merely reference it
            own_c = [ix for r, ix in sorted(ranked) if r < 99]
            cand = list(dict.fromkeys(own_c or [ix for _, ix in ranked]))[:40]
            if ids and not cand:
                # ids unknown to the output: not emitted (e.g. the --max-items cap) when this endpoint's ids join
                # elsewhere; else the parser re-keys -> judge by distinctive values
                dv = [c2[0] for pth, v2, _ in leaves(rec) if (c2 := canon(v2, last_key(pth))) and c2[1]]
                if ep_joins[ep] or (dv and sum(any(h(x) in H for x in url_variants(d)) for d in dv) < 0.5 * len(dv)):
                    not_emitted[ep] += 1
                    continue
            for path, v, _ in leaves(rec):
                lk = last_key(path)
                c = canon(v, lk)
                pkey = (scraper, ep, lpath + "." + ".".join(path))
                st = paths.get(pkey)
                if st is None:
                    st = paths[pkey] = {"present": 0, "null": 0, "kept": 0, "unjoined": 0, "sample": None}
                if c is None:
                    st["null"] += 1
                    continue
                st["present"] += 1
                if st["sample"] is None and not isinstance(v, (dict, list)):
                    st["sample"] = redact(v)
                cs, dist = c
                if dist:
                    if any(h(x) in H for x in url_variants(cs)):
                        st["kept"] += 1
                    continue
                if not cand:
                    st["unjoined"] += 1
                    if h(lk + "\x00" + cs) in G:
                        st["kept"] += 1
                    continue
                hp = h(lk + "\x00" + cs)
                hv = h(cs)
                if any(hp in slot_pairs[s] for s in cand) or \
                        any(keysim(lk, k2) for s in cand for k2 in slot_vals[s].get(hv, ())):
                    st["kept"] += 1
            f = feats(rec)
            raw_users.update(u for u in f["users"] if not u.startswith("key:"))
            if not gen_like(f):
                continue
            of = union_feats([slot_feats[c] for c in cand]) if cand else None
            _add_cov(raw_cov[(scraper, ep, f["model"] or "(none)", primary_kind(f))], f, of)
            if f["users"]:
                users.append((ep, "raw", f["users"]))
            if of is not None and of["users"]:
                users.append((ep, "out:" + slot_kind[cand[0]], of["users"]))
        del body
    return {"run": os.path.basename(run.rstrip("/\\")), "scraper": scraper, "paths": paths,
            "raw_cov": raw_cov, "out_cov": out_cov, "nonjson": nonjson, "users": users,
            "not_emitted": not_emitted, "raw_n": raw_n,
            "key_schemes": Counter({"raw_clerk_ids": len(raw_users),
                                    "out_clerk_id": sum(u in out_users for u in raw_users),
                                    "out_key_user": sum("key:" + make_id("user", u) in out_users for u in raw_users),
                                    "out_key_creator": sum("key:" + make_id("creator", u) in out_users for u in raw_users)})}


def make_id(*parts: Any) -> str:
    """Same as higgsfield_scraper.schemas.common.make_id (copied: this script must not import the package)."""
    key = "|".join("" if p is None else str(p).strip().lower() for p in parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _raw_env(rf: str) -> dict | None:
    try:
        with open(rf, encoding="utf-8") as f:
            env = json.load(f)
        return env if isinstance(env, dict) else None
    except (OSError, ValueError):
        return None


def _raw_body(rf: str) -> Any:
    env = _raw_env(rf)
    if env is None:
        return None
    b = env.get("body")
    if isinstance(b, str):
        return maybe_json(b)
    return b


COV_FIELDS = ("n", "prompt", "neg", "enh", "multi", "media", "inputs", "model", "settings_keys", "cost",
              "eng", "lineage", "ts", "status", "template")


def _add_cov(c: Counter, f: dict, of: dict | None) -> None:
    c["n"] += 1
    flags = {"prompt": f["prompt"], "neg": f["neg"], "enh": f["enh"], "multi": f["nprompts"] > 1,
             "media": f["out_urls"] > 0, "inputs": f["inputs"] > 0, "model": f["model"] is not None,
             "cost": f["cost"], "eng": bool(f["eng"]), "lineage": f["lineage"], "ts": f["ts"],
             "status": f["status"], "template": f["template"]}
    for k, v in flags.items():
        if v:
            c[k] += 1
    c["settings_keys"] += len(f["settings"])
    for v in f["variants"]:
        c["v:" + v] += 1
    for m in f["mkinds"]:
        c["k:" + m] += 1
    for r in f["roles"]:
        c["r:" + r] += 1
    for e in f["eng"]:
        c["e:" + e] += 1
    if of is None:
        c["unjoined"] += 1
        return
    c["joined"] += 1
    oflags = {"prompt": of["prompt"], "neg": of["neg"], "enh": of["enh"], "multi": of["nprompts"] > 1,
              "media": of["out_urls"] > 0, "inputs": of["inputs"] > 0, "model": of["model"] is not None,
              "cost": of["cost"], "eng": bool(of["eng"]), "lineage": of["lineage"], "ts": of["ts"],
              "status": of["status"], "template": of["template"]}
    for k, v in flags.items():
        if v and not oflags[k]:
            c["lost:" + k] += 1
    for v in {var for hu, var in f["urlv"].items() if hu not in of["allurls"]}:
        c["lostv:" + v] += 1
    if f["inurls"] - of["allurls"]:
        c["lost:input_urls"] += 1
    if f["settings"] - of["settings"]:
        c["lost:settings_keys"] += 1


# ------------------------------------------------------------------ report
def pct(a: int, n: int) -> str:
    return "-" if not n else f"{100 * a / n:.0f}%"


def merge(results: list[dict]) -> dict:
    paths: dict[tuple, dict] = {}
    raw_cov: dict[tuple, Counter] = defaultdict(Counter)
    out_cov: dict[tuple, Counter] = defaultdict(Counter)
    nonjson = Counter()
    users = []
    not_emitted = Counter()
    raw_n = Counter()
    key_schemes: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        key_schemes[r["scraper"]].update(r["key_schemes"])
        not_emitted.update({(r["scraper"], k): v for k, v in r["not_emitted"].items()})
        raw_n.update({(r["scraper"], k): v for k, v in r["raw_n"].items()})
        for k, st in r["paths"].items():
            t = paths.setdefault(k, {"present": 0, "null": 0, "kept": 0, "unjoined": 0, "sample": None, "runs": set()})
            for f in ("present", "null", "kept", "unjoined"):
                t[f] += st[f]
            t["sample"] = t["sample"] or st["sample"]
            t["runs"].add(r["run"])
        for k, c in r["raw_cov"].items():
            raw_cov[k].update(c)
        for k, c in r["out_cov"].items():
            out_cov[(r["scraper"],) + k].update(c)
        nonjson.update({(r["scraper"], k): v for k, v in r["nonjson"].items()})
        users.extend((r["scraper"],) + u for u in r["users"])
    return {"paths": paths, "raw_cov": raw_cov, "out_cov": out_cov, "nonjson": nonjson, "users": users,
            "not_emitted": not_emitted, "raw_n": raw_n, "key_schemes": key_schemes}


def render(m: dict, baseline: dict | None, title: str, max_dropped: int) -> str:
    L: list[str] = [f"## {title}", ""]
    hdr = ("| n | joined | prompt | neg | enh | media (variants) | kinds | inputs (roles) | model | avg settings | cost | "
           "engagement | lineage | ts | status | template | lost in output |")
    sep = "|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|"

    def row(c: Counter) -> str:
        n = c["n"]
        var = ",".join(f"{x[2:]}:{pct(c[x], n)}" for x in sorted(c) if x.startswith("v:"))
        kinds = ",".join(f"{x[2:]}:{c[x]}" for x in sorted(c) if x.startswith("k:"))
        roles = ",".join(sorted({x[2:] for x in c if x.startswith("r:")}))[:80]
        eng = ",".join(sorted({x[2:] for x in c if x.startswith("e:")}))
        lost = ", ".join(f"{x.split(':', 1)[1]}:{c[x]}" for x in sorted(c) if x.startswith(("lost:", "lostv:")))
        return (f"{n} | {pct(c['joined'], n)} | {pct(c['prompt'], n)} | {pct(c['neg'], n)} | "
                f"{pct(c['enh'], n)} | {pct(c['media'], n)} ({var}) | {kinds} | {pct(c['inputs'], n)} ({roles}) | "
                f"{pct(c['model'], n)} | {c['settings_keys'] / n:.1f} | {pct(c['cost'], n)} | {pct(c['eng'], n)} {eng} | "
                f"{pct(c['lineage'], n)} | {pct(c['ts'], n)} | {pct(c['status'], n)} | {pct(c['template'], n)} | {lost or '-'} |")

    # by area and by media kind (rolled up over models)
    by_area: dict[tuple, Counter] = defaultdict(Counter)
    by_kind: dict[tuple, Counter] = defaultdict(Counter)
    for k, c in m["raw_cov"].items():
        by_area[(area_of(k[0], k[1]), k[0], k[1])].update(c)
        by_kind[(k[3], k[0], k[1])].update(c)
    L += ["### Coverage per area (raw records rolled up over models)", "", "| area | scraper | endpoint " + hdr,
          "|---|---|---" + sep]
    for k in sorted(by_area):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | " + row(by_area[k]))
    L += ["", "### Coverage per primary media kind (video / image / audio / 3d-file / other)", "",
          "| kind | scraper | endpoint " + hdr, "|---|---|---" + sep]
    for k in sorted(by_kind):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | " + row(by_kind[k]))
    # coverage (raw side, with missing-in-output)
    L += ["", "### Coverage per source endpoint x model (raw records; `lost` = raw has it, output does not)", "",
          "| scraper | endpoint | model / job_set_type | kind " + hdr, "|---|---|---|---" + sep]
    for k in sorted(m["raw_cov"], key=lambda k: (k[0], k[1], -m["raw_cov"][k]["n"])):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | " + row(m["raw_cov"][k]))
    L += ["", "### Coverage per output kind x model (output records)", "",
          "| scraper | output kind | model | n | prompt | neg | media (variants) | kinds | inputs | model | avg settings | cost | engagement | lineage |",
          "|---|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|"]
    for k in sorted(m["out_cov"], key=lambda k: (k[0], k[1], -m["out_cov"][k]["n"])):
        c = m["out_cov"][k]
        n = c["n"]
        var = ",".join(f"{x[2:]}:{pct(c[x], n)}" for x in sorted(c) if x.startswith("v:"))
        kinds = ",".join(f"{x[2:]}:{c[x]}" for x in sorted(c) if x.startswith("k:"))
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {n} | {pct(c['prompt'], n)} | {pct(c['neg'], n)} | {pct(c['media'], n)} ({var}) | {kinds} | "
                 f"{pct(c['inputs'], n)} | {pct(c['model'], n)} | {c['settings_keys'] / n:.1f} | {pct(c['cost'], n)} | "
                 f"{pct(c['eng'], n)} | {pct(c['lineage'], n)} |")
    # dropped paths
    L += ["", "### Raw paths dropped (kept < 50% of the times they carry a value)", "",
          "| class | scraper | endpoint | raw path | present | kept | sample |", "|---|---|---|---|---:|---:|---|"]
    rows = []
    json_kept = {(sc, ep, p.split(".{json}", 1)[0]) for (sc, ep, p), st in m["paths"].items() if ".{json}" in p and st["kept"]}
    for (sc, ep, p), st in m["paths"].items():
        if st["present"] == 0 or (sc, ep, p) in json_kept:
            continue
        if st["kept"] / st["present"] < 0.5:
            rows.append((classify(p), sc, ep, p, st))
    order = {"valuable": 0, "unknown": 1, "technical metadata": 2, "intentional (ui/internal)": 3, "intentional (personal)": 4}
    # collapse dynamic-key families (e.g. `.titles.<nanoid>`): >8 dropped siblings under one parent -> one row
    def randomish(k: str) -> bool:
        return bool(re.fullmatch(r"[-\w]{5,10}", k)) and (any(ch.isdigit() for ch in k) or k.startswith("-"))             and not re.fullmatch(r"[a-z]+(_[a-z]+)*\d*", k)
    fam = Counter((r[1], r[2], r[3].rsplit(".", 1)[0]) for r in rows if randomish(r[3].rsplit(".", 1)[-1]))
    out_rows, seen_fam = [], set()
    for r in rows:
        par = r[3].rsplit(".", 1)[0]
        if fam[(r[1], r[2], par)] > 8:
            if (r[1], r[2], par) in seen_fam:
                continue
            seen_fam.add((r[1], r[2], par))
            r = (r[0], r[1], r[2], par + ".{*" + str(fam[(r[1], r[2], par)]) + " keys}", r[4])
        out_rows.append(r)
    rows = out_rows
    rows.sort(key=lambda r: (order[r[0]], r[1], r[2], r[3]))
    cnt = Counter(r[0] for r in rows)
    for r in rows[:max_dropped]:
        st = r[4]
        sample = "(not shown)" if r[0] == "intentional (personal)" or re.search(
            r"name|handle|collaborat|location|author|owner|workspace", r[3].rsplit(".", 1)[-1]) else (st["sample"] or "")
        L.append(f"| {r[0]} | {r[1]} | {r[2]} | `{r[3]}` | {st['present']} | {st['kept']} | {sample} |")
    L += ["", f"Dropped path counts: {dict(cnt)} (table capped at {max_dropped} rows).", ""]
    if m["not_emitted"]:
        L += ["Raw records with no trace in the output (not emitted: usually the `--max-items` cap stopped item "
              "emission while pages were still fetched; else a whole list the parser ignores):", "",
              "| scraper | endpoint | raw records | not emitted |", "|---|---|---:|---:|"]
        for k in sorted(m["not_emitted"]):
            L.append(f"| {k[0]} | {k[1]} | {m['raw_n'][k]} | {m['not_emitted'][k]} |")
        L.append("")
    if m["nonjson"]:
        L += ["Non-JSON raw bodies (HTML/text, not leaf-audited): " +
              ", ".join(f"{k[0]}/{k[1]}={v}" for k, v in sorted(m["nonjson"].items())), ""]
    L += ["### Creator key scheme per scraper (raw Clerk ids -> what the output carries)", "",
          "| scraper | raw Clerk ids | output keeps Clerk id | sha256('user/id')[:16] | sha256('creator/id')[:16] |",
          "|---|---:|---:|---:|---:|"]
    for sc, c in sorted(m["key_schemes"].items()):
        L.append(f"| {sc} | {c['raw_clerk_ids']} | {c['out_clerk_id']} | {c['out_key_user']} | {c['out_key_creator']} |")
    L.append("")
    # user key consistency
    L += ["### Creator key forms per source", "", "| scraper | endpoint | side | raw Clerk ids | hashed keys |", "|---|---|---|---:|---:|"]
    uk: dict[tuple, Counter] = defaultdict(Counter)
    for sc, ep, side, us in m["users"]:
        for u in us:
            uk[(sc, ep, side)]["key" if u.startswith("key:") else "clerk"] += 1
    for k in sorted(uk):
        L.append(f"| {k[0]} | {k[1]} | {k[2]} | {uk[k]['clerk']} | {uk[k]['key']} |")
    L.append("")
    # new raw paths vs baseline
    if baseline is not None:
        old = {(ep, p) for (_, ep, p) in baseline["paths"]}
        old_eps = {ep for (ep, _) in old}
        new = sorted({(sc, ep, p) for (sc, ep, p), st in m["paths"].items()
                      if st["present"] and ep in old_eps and (ep, p) not in old})
        L += ["### Raw paths seen now but not in the baseline runs (same endpoints)", "",
              "| scraper | endpoint | new raw path | kept in output? | sample |", "|---|---|---|---|---|"]
        for sc, ep, p in new[:max_dropped]:
            st = m["paths"][(sc, ep, p)]
            L.append(f"| {sc} | {ep} | `{p}` | {pct(st['kept'], st['present'])} | {st['sample'] or ''} |")
        L += ["", f"{len(new)} new paths; endpoints only in the new runs: "
              + ", ".join(sorted({ep for (_, ep, _) in m['paths']} - old_eps)), ""]
    return "\n".join(L)


def to_jsonable(m: dict) -> dict:
    return {"paths": [{"scraper": k[0], "endpoint": k[1], "path": k[2], **{x: (sorted(y) if isinstance(y, set) else y) for x, y in v.items()},
                       "class": classify(k[2])} for k, v in m["paths"].items()],
            "raw_cov": [{"key": list(k), **dict(c)} for k, c in m["raw_cov"].items()],
            "out_cov": [{"key": list(k), **dict(c)} for k, c in m["out_cov"].items()]}


def expand(args: list[str]) -> list[str]:
    out = []
    for a in args:
        hits = sorted(glob.glob(a)) or [a]
        out += [x for x in hits if os.path.isdir(os.path.join(x, "raw")) and os.path.isdir(os.path.join(x, "output"))]
    return list(dict.fromkeys(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="+", help="run folders (globs ok) with raw/ + output/")
    ap.add_argument("--baseline", nargs="*", default=None, help="older runs: list raw paths that are new since")
    ap.add_argument("--title", default="Completeness audit")
    ap.add_argument("--md", help="write the Markdown tables here (default: stdout)")
    ap.add_argument("--json", help="write the aggregates as JSON here")
    ap.add_argument("--max-dropped", type=int, default=400, help="row cap for the dropped / new path tables")
    a = ap.parse_args(argv)
    runs = expand(a.runs)
    if not runs:
        print("no run folders with raw/ + output/", file=sys.stderr)
        return 2
    res = []
    for r in runs:
        print(f"auditing {r}", file=sys.stderr)
        res.append(audit_run(r, log=print))
    m = merge(res)
    base = None
    if a.baseline:
        base = merge([audit_run(r) for r in expand(a.baseline)])
    md = render(m, base, a.title + f" ({len(runs)} runs: {', '.join(os.path.basename(r) for r in runs)[:400]})", a.max_dropped)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(to_jsonable(m), f, indent=4, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
