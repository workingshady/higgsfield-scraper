"""Generic record -> export row normalisation (works for any scraper's tables).

An `ExportRow` is one record of one collection, with the fields every layout needs pulled out generically:
prompt / caption, model, media type, primary media URL + thumbnail URL, size, provenance and dedup keys.
Nothing is invented: every value comes from the record (or the run's meta for provenance fallbacks).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

from . import keys as K

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".heic", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT | AUDIO_EXT
PDF_EXT = {".pdf"}

FULL_FIELDS = ("url", "media_url", "video_url", "result_url", "raw_url", "h264_url", "download_url", "file_url",
               "image_url", "audio_url")
THUMB_FIELDS = ("thumbnail_url", "min_url", "preview_url", "video_preview_url", "poster_url", "cover_url",
                "preview_image", "thumb_url")
LIST_FIELDS = ("results", "media", "variants", "outputs", "output")
SKIP_ROLES = re.compile(r"input|reference|avatar|icon|logo|start_image|end_image", re.I)
PROMPT_PATHS = ("prompt", "raw_params.prompt", "params.prompt", "settings.prompt")
CAPTION_PATHS = ("description", "text", "title", "name", "preset_name")
MODEL_PATHS = ("model_name", "made_with_model", "model_id", "job_set_type", "model_family", "tool", "model",
               "display_name")
AUTHOR_KEY_PATHS = ("author_key", "owner_key", "creator_key", "author.author_key", "creator.author_key")
DATE_PATHS = ("created_at", "published_at", "start_at", "updated_at")


def get_path(d: Any, path: str) -> Any:
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def first(d: dict, paths: Iterable[str], kind: type = str) -> Any:
    for p in paths:
        v = get_path(d, p)
        if isinstance(v, kind) and not isinstance(v, bool) and v not in ("", [], {}):
            return v
    return None


def ext_of(url: Optional[str]) -> str:
    if not url:
        return ""
    return os.path.splitext(urlsplit(url).path)[1].lower()


def media_kind(url: Optional[str], declared: Optional[str] = None) -> Optional[str]:
    e = ext_of(url)
    if e in IMAGE_EXT:
        return "image"
    if e in VIDEO_EXT:
        return "video"
    if e in AUDIO_EXT:
        return "audio"
    d = (declared or "").lower()
    for k in ("video", "image", "audio"):
        if k in d:
            return k
    return None


def is_media_url(u: Any) -> bool:
    return isinstance(u, str) and u.startswith(("http://", "https://")) and ext_of(u) in MEDIA_EXT


def _list_urls(rec: dict, thumbs: bool) -> list[str]:
    out: list[str] = []
    for lf in LIST_FIELDS:
        v = rec.get(lf)
        items = v if isinstance(v, list) else [v] if isinstance(v, dict) else []
        for m in items:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or m.get("name") or m.get("variant") or "")
            if SKIP_ROLES.search(role):
                continue
            is_thumb_role = bool(re.search(r"min|thumb|preview|poster", role, re.I))
            if thumbs:
                for f in ("thumbnail_url", "min_url", "poster_url", "preview_url"):
                    if is_media_url(m.get(f)):
                        out.append(m[f])
                if is_thumb_role and is_media_url(m.get("url")):
                    out.append(m["url"])
                ex = m.get("extra")
                if isinstance(ex, dict) and is_media_url(ex.get("poster_url")):
                    out.append(ex["poster_url"])
            elif not is_thumb_role and is_media_url(m.get("url")):
                out.append(m["url"])
    return out


def media_urls(rec: dict) -> tuple[list[str], list[str]]:
    """(full-size candidates, thumbnail candidates), best first, media URLs only (page URLs are ignored)."""
    full = [rec[f] for f in FULL_FIELDS if is_media_url(rec.get(f))]
    full += _list_urls(rec, thumbs=False)
    full += [u for u in K.output_urls(rec) if is_media_url(u)]
    thumbs = [rec[f] for f in THUMB_FIELDS if is_media_url(rec.get(f))] + _list_urls(rec, thumbs=True)
    full = list(dict.fromkeys(full))
    thumbs = [u for u in dict.fromkeys(thumbs) if u not in full[:1]]
    return full, thumbs


def _num(v: Any) -> Optional[float]:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v: Any) -> Optional[int]:
    """Arrow-friendly: one integer type per column (HF `datasets` infers the schema from the first rows)."""
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v == v else None


@dataclass
class ExportRow:
    scraper: str
    collection: str
    run_id: str
    record_id: str
    key: str                                   # rec:<scraper>:<collection>:<record_id>
    rec: dict
    gen_keys: list[str] = field(default_factory=list)
    prompt: Optional[str] = None
    caption: Optional[str] = None
    title: Optional[str] = None
    model: Optional[str] = None
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    thumb_url: Optional[str] = None
    all_urls: list[str] = field(default_factory=list)
    width: Optional[float] = None
    height: Optional[float] = None
    duration_seconds: Optional[float] = None
    created_at: Optional[str] = None
    source_url: Optional[str] = None
    scraped_at: Optional[str] = None
    schema_version: Any = None
    author_key: Optional[str] = None
    position: Optional[int] = None
    extra: dict = field(default_factory=dict)  # profile-specific normalized fields (contest, project, folder …)

    @property
    def date(self) -> Optional[str]:
        return self.created_at[:10] if isinstance(self.created_at, str) and len(self.created_at) >= 10 else None

    @property
    def has_prompt(self) -> bool:
        return bool(self.prompt)

    @property
    def caption_text(self) -> Optional[str]:
        """Text for the `.txt` sidecar: the generation prompt, else the record's description."""
        return self.prompt or (self.caption if self.caption and self.caption != self.title else None)

    def field(self, name: str) -> Any:
        """Value for --group-by / --filter: normalized field, profile extra, then a dotted path into the record."""
        if name in self.extra:
            return self.extra[name]
        if name == "date":
            return self.date
        if name == "has_prompt":
            return self.has_prompt
        if name == "has_media":
            return bool(self.media_url or self.thumb_url)
        if name in self.__dataclass_fields__ and name not in ("rec", "extra"):
            return getattr(self, name)
        return get_path(self.rec, name)

    def flat(self) -> dict[str, Any]:
        """Flat, Arrow-friendly metadata (scalars + JSON strings) for hf / jsonl / prompts.csv."""
        params = self.rec.get("params") or self.rec.get("settings") or self.rec.get("raw_params")
        d = {
            "id": self.record_id, "key": self.key, "scraper": self.scraper, "collection": self.collection,
            "title": self.title, "prompt": self.prompt, "caption": self.caption_text, "model": self.model,
            "media_type": self.media_type, "media_url": self.media_url, "thumbnail_url": self.thumb_url,
            "width": _int(self.width), "height": _int(self.height),
            "duration_seconds": float(self.duration_seconds) if self.duration_seconds is not None else None,
            "seed": _int(_num(self.rec.get("seed"))),
            "aspect_ratio": self.rec.get("aspect_ratio") if isinstance(self.rec.get("aspect_ratio"), str) else None,
            "created_at": self.created_at, "author_key": self.author_key,
            "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True) if params else None,
            "generation_keys": json.dumps(self.gen_keys) if self.gen_keys else None,
            "source_url": self.source_url, "scraped_at": self.scraped_at, "run_id": self.run_id,
            "schema_version": self.schema_version,
        }
        for k, v in self.extra.items():
            d.setdefault(k, v if not isinstance(v, (dict, list)) else json.dumps(v, ensure_ascii=False))
        return d


def build_row(scraper: str, coll: str, rec: dict, run_id: str, run_scraped_at: Optional[str],
              id_field: Optional[str] = None) -> ExportRow:
    rid = K.record_id(coll, rec, id_field)
    full, thumbs = media_urls(rec)
    media_url = full[0] if full else None
    declared = rec.get("media_type") if isinstance(rec.get("media_type"), str) else None
    src = rec.get("source") if isinstance(rec.get("source"), dict) else {}
    title = first(rec, ("title", "name", "preset_name", "display_name"))
    try:
        gk = K.generation_keys(scraper, coll, rec)
    except Exception:
        gk = []
    pos = rec.get("position")
    return ExportRow(
        scraper=scraper, collection=coll, run_id=run_id, record_id=rid, key=K.stable_key(scraper, coll, rid),
        rec=rec, gen_keys=list(gk),
        prompt=first(rec, PROMPT_PATHS), caption=first(rec, CAPTION_PATHS), title=title,
        model=first(rec, MODEL_PATHS),
        media_type=media_kind(media_url or (thumbs[0] if thumbs else None), declared) or declared,
        media_url=media_url, thumb_url=thumbs[0] if thumbs else None, all_urls=full + thumbs,
        width=_num(rec.get("width")) or _num(get_path(rec, "settings.width")),
        height=_num(rec.get("height")) or _num(get_path(rec, "settings.height")),
        duration_seconds=_num(rec.get("duration_seconds")) or _num(rec.get("duration")),
        created_at=first(rec, DATE_PATHS),
        source_url=rec.get("source_url") or src.get("url"),
        scraped_at=rec.get("scraped_at") or src.get("fetched_at") or run_scraped_at,
        schema_version=rec.get("schema_version"),
        author_key=first(rec, AUTHOR_KEY_PATHS) or ((rec.get("author_keys") or [None])[0]
                                                   if isinstance(rec.get("author_keys"), list) else None),
        position=pos if isinstance(pos, int) and not isinstance(pos, bool) else None,
    )
