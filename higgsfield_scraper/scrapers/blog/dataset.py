"""Assemble the BlogDataset and write outputs (JSON parts, complete CSVs, summary.md, articles/*.md)."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from ...core.base import RunMeta
from ...core.dataset import make_meta
from ...core.exporting import row, without, write_standard_outputs
from .endpoints import ENDPOINT_DOCS
from .options import Selection
from .schemas import BlogDataset

BODY_KEYS = ("content_format", "content_html", "content_markdown", "content_text", "content_blocks", "word_count",
             "headings", "links", "images")
COLLECTIONS = {               # dataset key -> (kind, id field)
    "posts": ("blog_post", "post_id"),
    "authors": ("blog_author", "slug"),
    "talent_posts": ("blog_talent_post", "post_id"),
    "community_posts": ("blog_community_post", "post_id"),
    "help_articles": ("blog_help_article", "article_id"),
    "case_studies": ("blog_case_study", "case_study_id"),
    "changelog": ("blog_changelog_entry", "entry_id"),
}


def _strip_kind(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "kind"}


def _sort_key(e: dict) -> tuple:
    d = e.get("published_at") or e.get("released_at") or e.get("updated_at") or ""
    return (str(d),)


def build_dataset(entities: dict[str, list[dict]], sel: Selection, rm: RunMeta) -> dict:
    contents = {c["post_id"]: c for c in entities.get("blog_post_content", [])}
    data: dict[str, list[dict]] = {}
    for coll, (kind, _id) in COLLECTIONS.items():
        data[coll] = [_strip_kind(e) for e in entities.get(kind, [])]

    for coll in ("talent_posts", "community_posts"):            # merge decoded bodies into their posts
        for p in data[coll]:
            c = contents.get(p["post_id"])
            if c:
                p.update({k: c.get(k) for k in BODY_KEYS if k in c})
                p["content_status"] = c.get("content_status") or "ok"

    # authors referenced by posts but without an author page (e.g. the "higgsfield" team author)
    known = {a["slug"] for a in data["authors"]}
    by_author: dict[str, list[str]] = {}
    refs: dict[str, dict] = {}
    for p in data["posts"]:
        a = p.get("author") or {}
        if a.get("slug"):
            by_author.setdefault(a["slug"], []).append(p["slug"])
            refs.setdefault(a["slug"], {**a, "source": p["source"]})
    for a in data["authors"]:
        if not a.get("post_slugs") and by_author.get(a["slug"]):
            a["post_slugs"] = by_author[a["slug"]]
            a["post_count"] = len(a["post_slugs"])
    for slug, a in refs.items():
        if slug not in known:
            data["authors"].append({
                "slug": slug, "author_id": a.get("id"), "name": a.get("name"), "position": a.get("position"),
                "url": f"https://higgsfield.ai/blog/author/{slug}", "post_count": len(by_author[slug]),
                "post_slugs": by_author[slug], "record_source": "post", "source": a["source"]})

    for coll in ("posts", "talent_posts", "community_posts", "case_studies", "changelog"):
        data[coll].sort(key=_sort_key, reverse=True)
    data["help_articles"].sort(key=lambda a: (a["section"], (a.get("category") or {}).get("order") or 99,
                                              a.get("category_slug") or "", a.get("order") or 999, a["slug"]))
    data["authors"].sort(key=lambda a: a["slug"].lower())

    posts = data["posts"]
    dates = sorted(str(p["published_at"]) for p in posts if p.get("published_at"))
    summary = {
        "posts_by_category": dict(Counter(((p.get("category") or {}).get("slug") or "none") for p in posts)),
        "help_articles_by_section": dict(Counter(a["section"] for a in data["help_articles"])),
        "help_articles_by_category": dict(Counter(f"{a['section']}/{a.get('category_slug')}"
                                                  for a in data["help_articles"])),
        "changelog_by_category": dict(Counter((c.get("category_slug") or "none") for c in data["changelog"])),
        "words_total": sum(int(x.get("word_count") or 0) for c in COLLECTIONS for x in data[c]),
        "with_content": {c: sum(1 for x in data[c] if x.get("content_text")) for c in COLLECTIONS if c != "authors"},
        "newest_post_at": dates[-1] if dates else None,
        "oldest_post_at": dates[0] if dates else None,
    }
    totals = dict(rm.totals)
    counts = {c: len(v) for c, v in data.items()}
    warnings = []
    errs = [p["post_id"] for c in ("talent_posts", "community_posts") for p in data[c]
            if str(p.get("content_status") or "").startswith("error")]
    if errs:
        warnings.append(f"{len(errs)} community/talent post bodies could not be decoded: {errs[:5]}")
    meta = make_meta("blog", sel, rm, counts=counts, endpoints=dict(ENDPOINT_DOCS), totals_available=totals,
                     warnings=warnings)
    ds = BlogDataset.model_validate({"schema_version": 1, "meta": meta, **data, "summary": summary})
    return ds.model_dump(mode="json")


# ------------------------------------------------------------------ CSV tables

def _body_less(e: dict, *extra: str) -> dict:
    return without(e, "headings", "links", "images", "content_blocks", "faq", "related_posts", "related_articles",
                   "hero_metrics", "tools_used", "chips", *extra)


def csv_tables(ds: dict) -> dict[str, tuple[list[dict], list[str]]]:
    t: dict[str, tuple[list[dict], list[str]]] = {}
    first = ["post_id", "slug", "title", "url"]
    t["posts"] = ([row(_body_less(p, "tags")) | {"tags": "|".join(p.get("tags") or [])} for p in ds["posts"]], first)
    t["authors"] = ([row(a) for a in ds["authors"]], ["slug", "name"])
    t["talent_posts"] = ([row(_body_less(p, "tags")) | {"tags": "|".join(p.get("tags") or []),
                                                        "related_posts": _j(p.get("related_posts"))}
                          for p in ds["talent_posts"]], first)
    t["community_posts"] = ([row(_body_less(p, "tags")) | {"tags": "|".join(p.get("tags") or []),
                                                           "related_posts": _j(p.get("related_posts"))}
                             for p in ds["community_posts"]], first)
    t["help_articles"] = ([row(_body_less(a, "search_keywords", "breadcrumbs"))
                           | {"search_keywords": "|".join(a.get("search_keywords") or []),
                              "breadcrumbs": " > ".join(a.get("breadcrumbs") or [])} for a in ds["help_articles"]],
                          ["article_id", "section", "category_slug", "slug", "title", "url"])
    t["case_studies"] = ([row(_body_less(c)) for c in ds["case_studies"]], ["case_study_id", "slug", "title", "url"])
    t["changelog"] = ([row(_body_less(c, "search_keywords")) | {"search_keywords": "|".join(c.get("search_keywords") or [])}
                       for c in ds["changelog"]], ["entry_id", "anchor", "title", "released_at"])

    # child tables (parent keys first)
    parents = [("post", "posts", "post_id"), ("talent_post", "talent_posts", "post_id"),
               ("community_post", "community_posts", "post_id"), ("help_article", "help_articles", "article_id"),
               ("case_study", "case_studies", "case_study_id"), ("changelog", "changelog", "entry_id")]
    for prefix, coll, idf in parents:
        for child in ("headings", "links", "images"):
            t[f"{prefix}_{child}"] = ([row(x, **{idf: p[idf], "position": i})
                                       for p in ds[coll] for i, x in enumerate(p.get(child) or [])], [idf, "position"])
    t["post_tags"] = ([{"post_id": p["post_id"], "tag": tg} for p in ds["posts"] for tg in p.get("tags") or []]
                      + [{"post_id": p["post_id"], "tag": tg} for c in ("talent_posts", "community_posts")
                         for p in ds[c] for tg in p.get("tags") or []], ["post_id"])
    for prefix, coll, idf, key in (("post", "posts", "post_id", "related_posts"),
                                   ("case_study", "case_studies", "case_study_id", "related_posts"),
                                   ("help_article", "help_articles", "article_id", "related_articles")):
        t[f"{prefix}_related"] = ([row(x, **{idf: p[idf], "position": i}) for p in ds[coll]
                                   for i, x in enumerate(p.get(key) or [])], [idf, "position"])
    for prefix, coll, idf in (("post", "posts", "post_id"), ("help_article", "help_articles", "article_id"),
                              ("case_study", "case_studies", "case_study_id")):
        t[f"{prefix}_faq"] = ([row(x, **{idf: p[idf], "position": i}) for p in ds[coll]
                               for i, x in enumerate(p.get("faq") or [])], [idf, "position"])
    t["case_study_metrics"] = ([row(m, case_study_id=c["case_study_id"], position=i) for c in ds["case_studies"]
                                for i, m in enumerate(c.get("hero_metrics") or [])], ["case_study_id", "position"])
    t["case_study_tools"] = ([row(m, case_study_id=c["case_study_id"], position=i) for c in ds["case_studies"]
                              for i, m in enumerate(c.get("tools_used") or [])], ["case_study_id", "position"])
    t["changelog_chips"] = ([row(m, entry_id=c["entry_id"], position=i) for c in ds["changelog"]
                             for i, m in enumerate(c.get("chips") or [])], ["entry_id", "position"])
    t["user_post_blocks"] = ([{"post_id": p["post_id"], "feed": p["feed"], "content_blocks": _j(p.get("content_blocks"))}
                              for c in ("talent_posts", "community_posts") for p in ds[c]
                              if p.get("content_blocks") is not None], ["post_id"])
    return t


def _j(v: Any) -> Optional[str]:
    import json
    return None if v is None else json.dumps(v, ensure_ascii=False)


# ------------------------------------------------------------------ summary + markdown articles

def summary_md(ds: dict) -> str:
    m, s = ds["meta"], ds["summary"]
    lines = [f"# Higgsfield blog & help content — {m.get('label') or m.get('run_id') or ''}", "",
             f"Scraped at {m['scraped_at']}. Options: `{m['options']}`.", "", "| collection | items | with text |",
             "|---|---:|---:|"]
    for c in COLLECTIONS:
        lines.append(f"| {c} | {len(ds[c])} | {s['with_content'].get(c, '')} |")
    lines += ["", f"Words of article text: {s['words_total']:,}.", ""]
    if s["posts_by_category"]:
        lines += ["## Blog posts by category", ""] + [f"- {k}: {v}" for k, v in
                                                      sorted(s["posts_by_category"].items(), key=lambda x: -x[1])]
        lines += ["", f"Newest post: {s['newest_post_at']}, oldest: {s['oldest_post_at']}", ""]
    if s["help_articles_by_category"]:
        lines += ["## Help articles by category", ""] + [f"- {k}: {v}" for k, v in
                                                         sorted(s["help_articles_by_category"].items())]
        lines.append("")
    if s["changelog_by_category"]:
        lines += ["## Changelog entries by category", ""] + [f"- {k}: {v}" for k, v in
                                                             sorted(s["changelog_by_category"].items())]
        lines.append("")
    if m.get("totals_available"):
        lines += ["## Totals reported by the sources", ""] + [f"- {k}: {v}" for k, v in m["totals_available"].items()]
        lines.append("")
    if m.get("limits_hit") or m.get("warnings"):
        lines += ["## Limits / warnings", ""] + [f"- {x}" for x in m.get("limits_hit", []) + m.get("warnings", [])]
        lines.append("")
    lines += ["Readable copies of every article: `articles/<collection>/<slug>.md`.", ""]
    return "\n".join(lines)


def _fname(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:120] or "item"


def _yaml(v: Any) -> str:
    import json
    return json.dumps(v, ensure_ascii=False)


def article_markdown(item: dict, coll: str) -> str:
    fm = {"title": item.get("title"), "url": item.get("url"),
          "id": item.get("post_id") or item.get("article_id") or item.get("case_study_id") or item.get("entry_id"),
          "category": (item.get("category") or {}).get("title") if isinstance(item.get("category"), dict) else None,
          "author": ((item.get("author") or {}).get("name") or (item.get("author") or {}).get("username"))
          if isinstance(item.get("author"), dict) else None,
          "published_at": item.get("published_at") or item.get("released_at"), "updated_at": item.get("updated_at"),
          "reading_time_minutes": item.get("reading_time_minutes"), "word_count": item.get("word_count"),
          "collection": coll}
    out = ["---"] + [f"{k}: {_yaml(v)}" for k, v in fm.items() if v not in (None, "")] + ["---", ""]
    title = item.get("title") or item.get("slug") or ""
    md = item.get("content_markdown") or ""
    if not md.lstrip().startswith("# "):
        out += [f"# {title}", ""]
    if item.get("subtitle") and coll in ("posts", "case_studies"):
        out += [f"> {item['subtitle']}", ""]
    if item.get("summary") and coll == "changelog":
        out += [f"*{item['summary']}*", ""]
    out.append(md or "_(no article text in this run — use --with-content)_")
    if item.get("faq"):
        out += ["", "## FAQ", ""]
        for f in item["faq"]:
            out += [f"### {f['question']}", "", f.get("answer_text") or "", ""]
    return "\n".join(out).rstrip() + "\n"


def write_articles(ds: dict, out_dir: Path) -> list[Path]:
    files = []
    for coll in ("posts", "talent_posts", "community_posts", "help_articles", "case_studies", "changelog"):
        d = out_dir / "articles" / coll
        used: set[str] = set()
        for it in ds[coll]:
            base = it.get("slug") or it.get("anchor") or it.get("post_id") or it.get("entry_id") or "item"
            if coll == "help_articles":
                base = f"{it['section']}__{it.get('category_slug') or 'x'}__{base}"
            name = _fname(base)
            if name in used:
                name = _fname(f"{base}-{(it.get('post_id') or it.get('entry_id') or it.get('article_id') or '')[:8]}")
            used.add(name)
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{name}.md"
            p.write_text(article_markdown(it, coll), encoding="utf-8")
            files.append(p)
    return files


def write_outputs(ds: dict, out_dir: Path) -> list[Path]:
    parts = {c: ds[c] for c in COLLECTIONS}
    parts["summary"] = ds["summary"]
    files = write_standard_outputs(ds, out_dir, json_parts=parts, csv_tables=csv_tables(ds),
                                   dataset_model=BlogDataset, summary_md=summary_md(ds))
    if (ds["meta"].get("options") or {}).get("write_markdown", True):
        files += write_articles(ds, out_dir)
    return files
