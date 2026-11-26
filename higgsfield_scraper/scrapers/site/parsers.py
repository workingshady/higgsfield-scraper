"""Pure parsers: Envelope -> entity dicts (each with "kind"). No network, no Scrapy.

Envelope bodies (the spider converts HTML / XML before archiving them):
* SSR pages: {"format": "tsr", "path", "page_type", "sitemap_lastmod", "head", "matches": [{"i", "l"}],
  "main_html"?} (see extract.py); a saved page {"html": "...", "path": ..., "page_type": ...} is accepted too.
* Sitemaps: {"format": "sitemap", "urls": [{"loc", "lastmod"}]} — discovery only, no entities.
* JSON APIs (`datetime_settings`, `business_unlim`, `game_gift`): untouched API JSON.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit

from ...core.dataset import make_id
from ...raw import Envelope
from ..blog.content import convert_html
from ..blog.parsers import extract_sitemap, iso
from .endpoints import (LANDING_EXCLUDE_EXACT, LANDING_EXCLUDE_PREFIXES, SITE)
from .extract import loader, page_body
from .hast import to_html
from .options import Selection
from .schemas import PRIMARY_KINDS

BOILERPLATE_HEADINGS = ("Explore more AI features", "AI-native creative suite")


# ================================================================== helpers

def _s(v: Any) -> Optional[str]:
    if v is None or isinstance(v, (dict, list)):
        return None
    s = str(v).strip()
    return s or None


def _int(v: Any) -> Optional[int]:
    try:
        return None if v in (None, "") or isinstance(v, bool) else int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v: Any) -> Optional[float]:
    try:
        return None if v in (None, "") or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def _dec(v: Any) -> Optional[str]:
    if v in (None, "") or isinstance(v, bool):
        return None
    try:
        return str(Decimal(str(v)))
    except (InvalidOperation, ValueError):
        return None


def _bool(v: Any) -> Optional[bool]:
    return v if isinstance(v, bool) else None


def _list(v: Any) -> list:
    return v if isinstance(v, list) else []


def _dicts(v: Any) -> list[dict]:
    return [x for x in _list(v) if isinstance(x, dict)]


def _strs(v: Any) -> list[str]:
    return [s for s in (_s(x) for x in _list(v)) if s]


def _extra(d: Any, used: Iterable[str]) -> dict[str, Any]:
    if not isinstance(d, dict):
        return {}
    used = set(used)
    return {k: v for k, v in d.items() if k not in used and v not in (None, "", [], {})}


def _abs(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    return u if u.startswith("http") else SITE + (u if u.startswith("/") else "/" + u)


def media(m: Any, *, url_keys=("url", "source", "src"), thumb_keys=("thumbnail", "thumbnail_url", "poster_url",
                                                                      "poster")) -> Optional[dict]:
    if isinstance(m, str):
        return {"url": m, "type": None, "thumbnail_url": None, "width": None, "height": None}
    if not isinstance(m, dict):
        return None
    url = next((m[k] for k in url_keys if isinstance(m.get(k), str) and m.get(k)), None)
    thumb = next((m[k] for k in thumb_keys if isinstance(m.get(k), str) and m.get(k)), None)
    if not url and not thumb:
        return None
    w, h = _int(m.get("width")), _int(m.get("height"))
    return {"url": url, "type": _s(m.get("type") or m.get("kind")), "thumbnail_url": thumb,
            "width": w if w is None or w >= 0 else None, "height": h if h is None or h >= 0 else None}


def seo(head: Any) -> Optional[dict]:
    if not isinstance(head, dict):
        return None
    return {"page_title": _s(head.get("title")), "meta_description": _s(head.get("description")),
            "keywords": _s(head.get("keywords")), "canonical": _s(head.get("canonical")),
            "og_image": _s(head.get("og_image")), "robots": _s(head.get("robots"))}


def body_fields(html: Optional[str], fmt: str, sel: Selection, *, cut_boilerplate: bool = False) -> dict[str, Any]:
    if not sel.with_content or not html:
        return {}
    r = convert_html(html)
    md = r.get("content_markdown") or ""
    if cut_boilerplate:
        for h in BOILERPLATE_HEADINGS:
            m = re.search(r"^#{1,6}\s+" + re.escape(h), md, flags=re.M | re.I)
            if m:
                md = md[:m.start()].rstrip()
        if md != (r.get("content_markdown") or ""):
            from ..blog.content import markdown_to_text
            text = markdown_to_text(md)
            r["content_markdown"], r["content_text"] = md or None, text or None
            r["word_count"] = len(re.findall(r"\w+", text)) if text else 0
            r["headings"] = [h for h in r["headings"] if h.get("text") not in BOILERPLATE_HEADINGS]
    r["content_format"] = fmt
    return {k: r.get(k) for k in ("content_format", "content_markdown", "content_text", "word_count", "headings",
                                  "links", "images")}


def _path(env: Envelope, body: dict) -> str:
    return body.get("path") or env.params.get("path") or urlsplit(env.url).path


def _ld_nodes(head: dict) -> list[dict]:
    out: list[dict] = []
    for g in (head or {}).get("ld_json") or []:
        for node in (g.get("@graph") if isinstance(g, dict) and "@graph" in g else (g if isinstance(g, list) else [g])):
            if isinstance(node, dict):
                out.append(node)
    return out


def _ld_type(node: dict) -> list[str]:
    t = node.get("@type")
    return [str(x) for x in t] if isinstance(t, list) else ([str(t)] if t else [])


def faq_from_ld(head: dict) -> list[dict]:
    out = []
    for n in _ld_nodes(head):
        if "FAQPage" in _ld_type(n):
            for q in _dicts(n.get("mainEntity")):
                name = _s(q.get("name"))
                ans = q.get("acceptedAnswer") or {}
                if name:
                    txt = _s(ans.get("text")) if isinstance(ans, dict) else None
                    out.append({"question": name, "answer_text": _plain(txt), "answer_html": txt if txt and "<" in txt
                                else None})
    return out


def _plain(txt: Optional[str]) -> Optional[str]:
    if not txt:
        return None
    return convert_html(txt)["content_text"] if "<" in txt else txt


# ================================================================== apps

def _app_templates(p: dict, preset: str = "primary") -> list[dict]:
    out = []
    for role in ("image", "video", "animate"):
        t = p.get(f"{role}Template")
        if isinstance(t, dict):
            out.append({"role": role, "preset": preset, "preset_slug": _s(p.get("slug")), "slug": _s(t.get("slug")),
                        "cost_credits": _dec(t.get("cost")),
                        "input_types": [str(i.get("type")) for i in _dicts(t.get("inputs")) if i.get("type")]})
    return out


def _faqs(items: Any) -> list[dict]:
    out = []
    for it in _dicts(items):
        q = _s(it.get("question") or it.get("title"))
        a = _s(it.get("answer") or it.get("content") or it.get("description"))
        if q:
            out.append({"question": q, "answer_text": _plain(a), "answer_html": a if a and "<" in a else None})
    return out


APP_USED = {"id", "title", "name", "description", "shortDescription", "media", "type", "isOnlyVideoAllowed",
            "inputMedia", "slug", "imageTemplate", "videoTemplate", "animateTemplate", "author", "mediaDescription",
            "landingHowToTitle", "landingHowTo", "landingShowcase", "landingInfoTitle", "landingInfoDescription",
            "landingInfoItems", "landingFaqs", "landingCtaTitle", "landingCtaDescription"}


def app_record(p: dict, env: Envelope, sel: Selection, *, page: dict, head: Optional[dict]) -> dict:
    slug = _s(p.get("slug")) or _path(env, {}).rstrip("/").rsplit("/", 1)[-1]
    second = page.get("secondaryAppPreset") if isinstance(page.get("secondaryAppPreset"), dict) else None
    templates = _app_templates(p) + (_app_templates(second, "secondary") if second else [])
    costs = [Decimal(t["cost_credits"]) for t in templates if t["cost_credits"] is not None]
    author = p.get("author") if isinstance(p.get("author"), dict) else {}
    return {
        "kind": "site_app", "record_key": f"{slug}@page", "app_id": str(p.get("id") or make_id("app", slug)),
        "slug": slug, "url": f"{SITE}/apps/{slug}", "title": _s(p.get("title")), "name": _s(p.get("name")),
        "description": _s(p.get("description")), "short_description": _s(p.get("shortDescription")),
        "media_description": _s(p.get("mediaDescription")), "page_kind": _s(page.get("kind")),
        "slug_type": _s(page.get("slugType")), "preset_type": _s(p.get("type")),
        "is_only_video_allowed": _bool(p.get("isOnlyVideoAllowed")), "media": media(p.get("media")),
        "input_media": media(p.get("inputMedia")), "templates": templates,
        "min_cost_credits": str(min(costs)) if costs else None, "max_cost_credits": str(max(costs)) if costs else None,
        "author_name": _s(author.get("name")) if sel.with_profiles else None,
        "has_author": bool(_s(author.get("name"))),
        "landing_how_to_title": _s(p.get("landingHowToTitle")), "landing_how_to": _dicts(p.get("landingHowTo")),
        "landing_showcase": _dicts(p.get("landingShowcase")), "landing_info_title": _s(p.get("landingInfoTitle")),
        "landing_info_description": _s(p.get("landingInfoDescription")),
        "landing_info_items": _dicts(p.get("landingInfoItems")), "landing_faqs": _faqs(p.get("landingFaqs")),
        "landing_cta_title": _s(p.get("landingCtaTitle")), "landing_cta_description": _s(p.get("landingCtaDescription")),
        "secondary_preset_slug": _s(second.get("slug")) if second else None, "seo": seo(head),
        "record_source": "page", "extra": _extra(p, APP_USED), "source": env.provenance(),
    }


def app_card(c: dict, env: Envelope, category: Optional[str]) -> Optional[dict]:
    slug = _s(c.get("slug"))
    if not slug:
        return None
    names = c.get("name")
    name = " ".join(_strs(names)) if isinstance(names, list) else _s(names)
    return {
        "kind": "site_app", "record_key": f"{slug}@index", "app_id": str(c.get("id") or make_id("app", slug)),
        "slug": slug, "url": f"{SITE}/apps/{slug}", "name": name, "media_description": _s(c.get("mediaDescription")),
        "category_slugs": [category] if category else [],
        "tags": [t for t in (_s(x.get("text")) for x in _dicts(c.get("tags"))) if t],
        "upload_date": iso(c.get("uploadDate")), "card_preview": media(c.get("preview")), "record_source": "index",
        "extra": _extra(c, {"id", "slug", "name", "mediaDescription", "tags", "uploadDate", "preview"}),
        "source": env.provenance(),
    }


def app_categories(l_: dict) -> list[dict]:
    return _dicts(l_.get("categories"))


def parse_apps_index(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "categories") or {}
    out: list[dict] = []
    for c in app_categories(l_):
        slug = _s(c.get("slug"))
        if not slug:
            continue
        cards = _dicts(c.get("apps"))
        out.append({"kind": "site_app_category", "category_id": str(c.get("id") or slug), "slug": slug,
                    "url": f"{SITE}/apps/{slug}", "name": _s(c.get("name")), "description": _s(c.get("description")),
                    "icon": _s(c.get("icon")), "priority": _int(c.get("priority")),
                    "app_slugs": [s for s in (_s(a.get("slug")) for a in cards) if s], "source": env.provenance()})
        for a in cards:
            r = app_card(a, env, slug)
            if r:
                out.append(r)
    return out


def parse_app_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    head = body.get("head")
    l_ = loader(body, "appPreset")
    if l_ and isinstance(l_.get("appPreset"), dict):
        return [app_record(l_["appPreset"], env, sel, page=l_, head=head)]
    l_ = loader(body, "initialCategoryData")          # a category page (/apps/<category-slug>)
    if l_:
        cat = _s(l_.get("activeCategory"))
        items = _dicts((l_.get("initialCategoryData") or {}).get("items"))
        return [r for r in (app_card(a, env, cat) for a in items) if r]
    return []


def app_category_slugs(body: Any) -> set[str]:
    l_ = loader(page_body(body), "categories") or {}
    return {s for s in (_s(c.get("slug")) for c in app_categories(l_)) if s}


def app_index_slugs(body: Any) -> list[str]:
    l_ = loader(page_body(body), "categories") or {}
    return list(dict.fromkeys(s for c in app_categories(l_) for s in (_s(a.get("slug")) for a in _dicts(c.get("apps")))
                              if s))


# ================================================================== academy

COURSE_USED = {"id", "slug", "title", "description", "difficulty", "duration_minutes", "reading_minutes",
               "lesson_count", "categories", "thumbnail", "preview_media", "has_certificate", "has_examples",
               "has_creator_drop", "featured_position", "published_at", "updated_at", "objectives", "authors",
               "metadata", "examples", "lessons", "certificate_unlocked"}


def course_record(c: dict, env: Envelope, sel: Selection, *, record_source: str, head: Optional[dict] = None) -> dict:
    slug = str(c.get("slug"))
    meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
    lessons = []
    for les in _dicts(c.get("lessons")):
        if not les.get("slug"):
            continue
        lessons.append({"lesson_id": str(les.get("id") or make_id("lesson", slug, les["slug"])),
                        "slug": str(les["slug"]), "url": f"{SITE}/academy/courses/{slug}/{les['slug']}",
                        "title": _s(les.get("title")), "position": _int(les.get("position")),
                        "reading_minutes": _int(les.get("reading_minutes")), "thumbnail_url": _s(les.get("thumbnail")),
                        "video_url": _s(les.get("video")), "homework_required": _bool(les.get("homework_required"))})
    authors = [{"name": _s(a.get("name")), "role": _s(a.get("role")), "bio": _s(a.get("bio")),
                "avatar_url": _s(a.get("avatar_url"))} for a in _dicts(c.get("authors"))]
    return {
        "kind": "site_academy_course", "record_key": f"{slug}@{record_source}",
        "course_id": str(c.get("id") or make_id("course", slug)), "slug": slug,
        "url": f"{SITE}/academy/courses/{slug}", "title": _s(c.get("title")), "description": _s(c.get("description")),
        "difficulty": _s(c.get("difficulty")), "duration_minutes": _int(c.get("duration_minutes")),
        "reading_minutes": _int(c.get("reading_minutes")), "lesson_count": _int(c.get("lesson_count")),
        "categories": _strs(c.get("categories")), "thumbnail_url": _s(c.get("thumbnail")),
        "preview_media": media(c.get("preview_media")), "has_certificate": _bool(c.get("has_certificate")),
        "has_examples": _bool(c.get("has_examples")), "has_creator_drop": _bool(c.get("has_creator_drop")),
        "featured_position": _int(c.get("featured_position")), "published_at": iso(c.get("published_at")),
        "updated_at": iso(c.get("updated_at")),
        "objectives": [{"title": str(o["title"]), "description": _s(o.get("description"))}
                       for o in _dicts(c.get("objectives")) if _s(o.get("title"))],
        "authors": authors, "skills": _strs(meta.get("skills")), "models": _strs(meta.get("models")),
        "languages": _strs(meta.get("languages")), "tools": _strs(meta.get("tools")),
        "examples": _dicts(c.get("examples")), "lessons": lessons, "seo": seo(head) if head else None,
        "record_source": record_source, "extra": _extra(c, COURSE_USED), "source": env.provenance(),
    }


def parse_academy_index(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    out: list[dict] = []
    l_ = loader(body, "categories") or {}
    for c in _dicts(l_.get("categories")):
        slug = _s(c.get("slug"))
        if slug:
            out.append({"kind": "site_academy_category", "category_id": str(c.get("id") or slug), "slug": slug,
                        "title": _s(c.get("title")), "description": _s(c.get("description")),
                        "artwork": _s(c.get("artwork")), "source": env.provenance()})
    courses = (loader(body, "allCourses") or {}).get("allCourses") or (loader(body, "courses") or {}).get("courses")
    for c in _dicts(courses):
        if c.get("slug"):
            out.append(course_record(c, env, sel, record_source="index"))
    return out


def academy_index_slugs(body: Any) -> list[str]:
    b = page_body(body)
    courses = (loader(b, "allCourses") or {}).get("allCourses") or (loader(b, "courses") or {}).get("courses")
    return [str(c["slug"]) for c in _dicts(courses) if c.get("slug")]


def parse_course_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "course")
    if not l_ or not isinstance(l_.get("course"), dict):
        return []
    return [course_record(l_["course"], env, sel, record_source="page", head=body.get("head"))]


def course_lesson_paths(body: Any) -> list[str]:
    l_ = loader(page_body(body), "course") or {}
    c = l_.get("course") if isinstance(l_.get("course"), dict) else {}
    return [f"/academy/courses/{c['slug']}/{x['slug']}" for x in _dicts(c.get("lessons")) if x.get("slug")
            and c.get("slug")]


LESSON_USED = {"access", "id", "slug", "title", "xp_reward", "progress_pct", "completed", "thumbnail", "video",
               "video_subtitles", "video_cues", "resources"}


def parse_lesson_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "lesson")
    if not l_ or not isinstance(l_.get("lesson"), dict):
        return []
    les, course = l_["lesson"], l_.get("course") if isinstance(l_.get("course"), dict) else {}
    summary = l_.get("summary") if isinstance(l_.get("summary"), dict) else {}
    path = _path(env, body)
    parts = path.strip("/").split("/")
    course_slug = _s(course.get("slug")) or (parts[2] if len(parts) > 2 else "")
    slug = _s(les.get("slug")) or parts[-1]
    nxt = (l_.get("nextLessonTarget") or {}) if isinstance(l_.get("nextLessonTarget"), dict) else {}
    tree = l_.get("mdxTree")
    e = {
        "kind": "site_academy_lesson", "lesson_id": str(les.get("id") or make_id("lesson", course_slug, slug)),
        "slug": slug, "course_slug": course_slug, "course_id": _s(course.get("id")),
        "course_title": _s(course.get("title")), "url": f"{SITE}/academy/courses/{course_slug}/{slug}",
        "title": _s(les.get("title")), "position": _int(summary.get("position")), "xp_reward": _int(les.get("xp_reward")),
        "reading_minutes": _int(summary.get("reading_minutes")), "thumbnail_url": _s(les.get("thumbnail")),
        "video_url": _s(les.get("video")), "video_poster_url": _s(summary.get("video_poster")),
        "video_subtitles": _dicts(les.get("video_subtitles")), "video_cues": _dicts(les.get("video_cues")),
        "resources": [{"type": _s(r.get("type")), "name": _s(r.get("name")), "download_url": _s(r.get("download_url")),
                       "thumbnail_url": _s(r.get("thumbnail_url")), "page_count": _int(r.get("page_count"))}
                      for r in _dicts(les.get("resources"))],
        "homework_required": _bool(summary.get("homework_required")),
        "access_allowed": _bool((les.get("access") or {}).get("allowed")) if isinstance(les.get("access"), dict) else None,
        "next_lesson_slug": _s((nxt.get("lesson") or {}).get("slug")) if isinstance(nxt.get("lesson"), dict) else None,
        "seo": seo(body.get("head")), "extra": _extra(les, LESSON_USED | {"progress_pct", "completed"}),
        "source": env.provenance(),
    }
    e["extra"].pop("progress_pct", None)
    e.update(body_fields(to_html(tree) if isinstance(tree, dict) else None, "hast", sel))
    return [e]


# ================================================================== MCP

def agents(items: Any) -> list[dict]:
    return [{"agent": str(a.get("id")), "destination": _s(a.get("destination")), "label": _s(a.get("label")),
             "prompt": _s(a.get("prompt")), "installations": _dicts(a.get("installations"))}
            for a in _dicts(items) if a.get("id")]


SKILL_USED = {"id", "slug", "title", "card_title", "skill_label", "description", "short_description",
              "overview_description", "detail_title", "external_url", "is_indexable", "tags", "cover_media", "cover_alt",
              "card_example", "agents", "apps", "installations", "main_conversation", "conversation_media", "medias",
              "tutorial_title", "tutorial_description", "tutorial_media", "reference_medias", "breadcrumb_label",
              "view_label"}


def skill_record(s: dict, env: Envelope, sel: Selection, *, record_source: str, head: Optional[dict] = None) -> dict:
    slug = str(s.get("slug"))
    conv = s.get("main_conversation") if isinstance(s.get("main_conversation"), dict) else {}
    result = conv.get("result") if isinstance(conv.get("result"), dict) else {}
    card = s.get("card_example") if isinstance(s.get("card_example"), dict) else {}
    return {
        "kind": "site_mcp_skill", "record_key": f"{slug}@{record_source}",
        "skill_id": str(s.get("id") or make_id("mcp", slug)), "slug": slug, "url": f"{SITE}/mcp/{slug}",
        "title": _s(s.get("title")), "card_title": _s(s.get("card_title")), "skill_label": _s(s.get("skill_label")),
        "description": _s(s.get("description")), "short_description": _s(s.get("short_description")),
        "overview_description": _s(s.get("overview_description")), "detail_title": _s(s.get("detail_title")),
        "external_url": _s(s.get("external_url")), "is_indexable": _bool(s.get("is_indexable")),
        "tags": [t for t in (_s(x.get("key") or x.get("name")) for x in _dicts(s.get("tags"))) if t],
        "cover_media": media(s.get("cover_media")), "cover_alt": _s(s.get("cover_alt")),
        "card_prompt": _s(card.get("prompt")), "agents": agents(s.get("agents")), "apps": _dicts(s.get("apps")),
        "installations": _dicts(s.get("installations")),
        "example_result": media(result.get("media")) or media(s.get("conversation_media")),
        "example_conversation": [{"message_id": _s(m.get("id")), "role": _s(m.get("role")), "text": _s(m.get("text")),
                                  "attachments": _dicts(m.get("attachments"))} for m in _dicts(conv.get("messages"))],
        "medias": [m for m in (media(x) for x in _list(s.get("medias"))) if m],
        "tutorial_title": _s(s.get("tutorial_title")), "tutorial_description": _s(s.get("tutorial_description")),
        "tutorial_media": media(s.get("tutorial_media")), "seo": seo(head) if head else None,
        "record_source": record_source, "extra": _extra(s, SKILL_USED), "source": env.provenance(),
    }


BUNDLE_USED = {"id", "slug", "title", "description", "badge_label", "skill_slugs", "prompt", "download_url",
               "chatgpt_url", "seo_title", "seo_description", "seo_image_url", "is_indexable", "all_presets_order",
               "cover_media", "agents"}


def bundle_record(b: dict, env: Envelope, *, record_source: str) -> dict:
    slug = str(b.get("slug"))
    return {
        "kind": "site_mcp_bundle", "bundle_id": str(b.get("id") or make_id("bundle", slug)), "slug": slug,
        "url": f"{SITE}/mcp/bundles/{slug}", "title": _s(b.get("title")), "description": _s(b.get("description")),
        "badge_label": _s(b.get("badge_label")), "skill_slugs": _strs(b.get("skill_slugs")), "prompt": _s(b.get("prompt")),
        "download_url": _s(b.get("download_url")), "chatgpt_url": _s(b.get("chatgpt_url")),
        "seo_title": _s(b.get("seo_title")), "seo_description": _s(b.get("seo_description")),
        "seo_image_url": _s(b.get("seo_image_url")), "is_indexable": _bool(b.get("is_indexable")),
        "all_presets_order": _int(b.get("all_presets_order")), "cover_media": media(b.get("cover_media")),
        "agents": agents(b.get("agents")), "record_source": record_source, "extra": _extra(b, BUNDLE_USED),
        "source": env.provenance(),
    }


def parse_mcp_index(env: Envelope, sel: Selection) -> list[dict]:
    l_ = loader(page_body(env.body), "items") or {}
    out = [skill_record(s, env, sel, record_source="index") for s in _dicts(l_.get("items")) if s.get("slug")]
    out += [bundle_record(b, env, record_source="index") for b in _dicts(l_.get("bundles")) if b.get("slug")]
    return out


def mcp_index_slugs(body: Any) -> tuple[list[str], list[str]]:
    l_ = loader(page_body(body), "items") or {}
    return ([str(s["slug"]) for s in _dicts(l_.get("items")) if s.get("slug")],
            [str(b["slug"]) for b in _dicts(l_.get("bundles")) if b.get("slug")])


def parse_mcp_skill(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "skill")
    if not l_ or not isinstance(l_.get("skill"), dict):
        return []
    return [skill_record(l_["skill"], env, sel, record_source="page", head=body.get("head"))]


def parse_mcp_bundle(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "bundle")
    if not l_ or not isinstance(l_.get("bundle"), dict):
        return []
    out = [bundle_record(l_["bundle"], env, record_source="page")]
    out += [skill_record(s, env, sel, record_source="index") for s in _dicts(l_.get("skills")) if s.get("slug")]
    return out


# ================================================================== original series

SERIES_USED = {"id", "slug", "title", "description", "fullDescription", "shortDescription", "authorType", "author",
               "isSeries", "state", "type", "categorySlugs", "tags", "durationSeconds", "engagement", "voteCount",
               "subscriberCount", "engagementScore", "firstEpisodeId", "firstEpisodeSlug", "projectPublicationId",
               "portraitUrl", "landscapeUrl", "backgroundUrl", "logoUrl", "trailerUrl", "trailerHlsUrl",
               "previewVideoUrl", "previewVideoHlsUrl", "cast", "isVoteTriggered", "isNotifyTriggered"}


def series_record(s: dict, env: Envelope, sel: Selection, *, in_hero: bool) -> dict:
    slug = str(s.get("slug"))
    eng = s.get("engagement") if isinstance(s.get("engagement"), dict) else {}
    first = _s(s.get("firstEpisodeSlug"))
    return {
        "kind": "site_original_series", "series_id": str(s.get("id") or make_id("series", slug)), "slug": slug,
        "url": f"{SITE}/original-series/{slug}" + (f"/{first}" if first else ""), "title": _s(s.get("title")),
        "description": _s(s.get("shortDescription") or s.get("description")),
        "full_description": _s(s.get("fullDescription")), "author_type": _s(s.get("authorType")),
        "series_type": _s(s.get("type")), "is_series": _bool(s.get("isSeries")), "state": _s(s.get("state")),
        "category_slugs": _strs(s.get("categorySlugs")), "tags": _strs(s.get("tags")),
        "duration_seconds": _int(s.get("durationSeconds")), "likes": _int(eng.get("likeCount")),
        "views": _int(eng.get("viewCount")), "comments": _int(eng.get("commentCount")),
        "vote_count": _int(s.get("voteCount")), "subscriber_count": _int(s.get("subscriberCount")),
        "engagement_score": _float(s.get("engagementScore")), "first_episode_id": _s(s.get("firstEpisodeId")),
        "first_episode_slug": first, "project_publication_id": _s(s.get("projectPublicationId")),
        "portrait_url": _s(s.get("portraitUrl")), "landscape_url": _s(s.get("landscapeUrl")),
        "background_url": _s(s.get("backgroundUrl")), "logo_url": _s(s.get("logoUrl")),
        "trailer_url": _s(s.get("trailerUrl")), "trailer_hls_url": _s(s.get("trailerHlsUrl")),
        "preview_video_url": _s(s.get("previewVideoUrl") or s.get("previewVideoHlsUrl")), "in_hero": in_hero,
        "cast": _dicts(s.get("cast")) if sel.with_profiles else [],
        "extra": _extra(s, SERIES_USED), "source": env.provenance(),
    }


def parse_originals_index(env: Envelope, sel: Selection) -> list[dict]:
    l_ = loader(page_body(env.body), "snapshot") or {}
    snap = l_.get("snapshot") if isinstance(l_.get("snapshot"), dict) else {}
    hero = {str(h.get("slug")) for h in _dicts((snap.get("hero") or {}).get("data"))}
    data = ((snap.get("originals") or {}).get("data") or {}) if isinstance(snap.get("originals"), dict) else {}
    items = _dicts(data.get("items")) if isinstance(data, dict) else []
    seen = {str(s.get("slug")) for s in items}
    items += [h for h in _dicts((snap.get("hero") or {}).get("data")) if str(h.get("slug")) not in seen]
    return [series_record(s, env, sel, in_hero=str(s.get("slug")) in hero) for s in items if s.get("slug")]


def originals_total(body: Any) -> Optional[int]:
    l_ = loader(page_body(body), "snapshot") or {}
    data = (((l_.get("snapshot") or {}).get("originals") or {}).get("data") or {})
    return _int(data.get("total")) if isinstance(data, dict) else None


EPISODE_USED = {"id", "slug", "user", "title", "description", "type", "likesCount", "dislikesCount", "viewsCount",
                "likeMark", "totalViews", "postUrls", "thumbnailSrc", "youtubeUrl", "isAdultsOnly", "videoSrc", "badges",
                "allEpisodes", "shimmerSrc", "createdAt"}


def parse_episode_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "episode")
    if not l_ or not isinstance(l_.get("episode"), dict):
        return []
    ep, proj = l_["episode"], l_.get("project") if isinstance(l_.get("project"), dict) else {}
    path = _path(env, body)
    parts = path.strip("/").split("/")
    series_slug = _s(l_.get("seriesSlug")) or (parts[1] if len(parts) > 1 else "")
    slug = _s(ep.get("slug")) or parts[-1]
    user = ep.get("user") if isinstance(ep.get("user"), dict) else {}
    return [{
        "kind": "site_original_episode", "episode_id": str(ep.get("id") or make_id("episode", series_slug, slug)),
        "slug": slug, "series_slug": series_slug, "series_id": _s(l_.get("seriesId")),
        "series_title": _s(l_.get("seriesTitle")), "url": f"{SITE}/original-series/{series_slug}/{slug}",
        "title": _s(ep.get("title")), "description": _s(ep.get("description")), "episode_type": _s(ep.get("type")),
        "likes": _int(ep.get("likesCount")), "dislikes": _int(ep.get("dislikesCount")),
        "views": _int(ep.get("viewsCount")), "total_views": _int(ep.get("totalViews")),
        "video_url": _s(ep.get("videoSrc")), "thumbnail_url": _s(ep.get("thumbnailSrc")),
        "youtube_url": _s(ep.get("youtubeUrl")), "is_adults_only": _bool(ep.get("isAdultsOnly")),
        "created_at": iso(ep.get("createdAt")),
        "episodes": [{"episode_id": _s(x.get("id")), "slug": _s(x.get("slug")), "title": _s(x.get("title")),
                      "video_url": _s(x.get("videoSrc")), "thumbnail_url": _s(x.get("thumbnailSrc")),
                      "duration": _float(x.get("duration"))} for x in _dicts(ep.get("allEpisodes"))],
        "project_id": _s(proj.get("id")), "project_slug": _s(proj.get("slug")), "project_title": _s(proj.get("title")),
        "project_type": _s(proj.get("type")), "project_views": _int(proj.get("views")),
        "project_likes": _int(proj.get("likes")), "project_created_at": iso(proj.get("createdAt")),
        "project_is_ongoing": _bool(proj.get("isOngoing")), "project_show_prompts": _bool(proj.get("showPrompts")),
        "uploader": _s(user.get("username")) if sel.with_profiles else None,
        "recommended_slugs": [s for s in (_s(r.get("slug")) for r in _dicts(l_.get("recommended"))) if s],
        "seo": seo(body.get("head")), "extra": _extra(ep, EPISODE_USED), "source": env.provenance(),
    }]


# ================================================================== mixed media presets

def parse_mixed_media_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    l_ = loader(body, "preset")
    if not l_ or not isinstance(l_.get("preset"), dict):
        return []
    p = l_["preset"]
    pid = _s(p.get("id")) or _path(env, body).rstrip("/").rsplit("/", 1)[-1]
    samples = []
    for it in _dicts(l_.get("initialItems")):
        job = it.get("job") if isinstance(it.get("job"), dict) else {}
        prof = it.get("profile") if isinstance(it.get("profile"), dict) else {}
        samples.append({"sample_id": str(it.get("id") or it.get("jobId")), "job_id": _s(it.get("jobId")),
                        "job_set_type": _s(job.get("jobSetType")), "media": media(it.get("media")),
                        "likes": _int(it.get("likes")),
                        "creator": _s(prof.get("username")) if sel.with_profiles else None})
    return [{"kind": "site_mixed_media_preset", "preset_id": pid, "url": f"{SITE}/mixed-media-presets/preset/{pid}",
             "name": _s(p.get("name")), "description": _s(p.get("description")), "sample_count": len(samples),
             "samples": samples, "samples_cursor": _float(l_.get("initialCursor")), "seo": seo(body.get("head")),
             "source": env.provenance()}]


# ================================================================== landings / rooms

def is_landing_path(path: str) -> bool:
    if path in LANDING_EXCLUDE_EXACT:
        return False
    return not any(path == p.rstrip("/") or path.startswith(p if p.endswith("/") else p + "/") or path == p
                   for p in LANDING_EXCLUDE_PREFIXES)


def _breadcrumbs(head: dict) -> list[str]:
    for n in _ld_nodes(head):
        if "BreadcrumbList" in _ld_type(n):
            return [str(i.get("name")) for i in _dicts(n.get("itemListElement")) if i.get("name")]
    return []


def _h_tags(html: Optional[str], tag: str) -> list[str]:
    if not html:
        return []
    out = []
    for m in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, flags=re.S | re.I):
        t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()
        t = convert_html(t)["content_text"] if "&" in t else t
        if t and t not in BOILERPLATE_HEADINGS:
            out.append(t)
    return list(dict.fromkeys(out))


def parse_landing(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    head = body.get("head") or {}
    path = _path(env, body).rstrip("/") or "/"
    ptype = body.get("page_type") or "landing"
    if ptype == "landing":
        ptype = "home" if path == "/" else ("plugin" if path.startswith("/plugins/") else "landing")
    nodes = _ld_nodes(head)
    app = next((n for n in nodes if "SoftwareApplication" in _ld_type(n) or "WebApplication" in _ld_type(n)), {})
    offer = app.get("offers") if isinstance(app.get("offers"), dict) else \
        (next(iter(_dicts(app.get("offers"))), {}) if app else {})
    howto = next((n for n in nodes if "HowTo" in _ld_type(n)), {})
    steps = [{"position": _int(st.get("position")) or i + 1, "name": _s(st.get("name")), "text": _s(st.get("text")),
              "image": _s(st.get("image")) if not isinstance(st.get("image"), dict) else _s(st["image"].get("url"))}
             for i, st in enumerate(_dicts(howto.get("step")))]
    cur = _s(offer.get("priceCurrency"))
    html = body.get("main_html")
    h1 = _h_tags(html, "h1")
    e = {
        "kind": "site_landing", "page_id": make_id("page", path), "path": path, "url": SITE + ("" if path == "/" else path),
        "page_type": ptype, "h1": h1[0] if h1 else _s(head.get("og_title")), "sections": _h_tags(html, "h2"),
        "breadcrumbs": _breadcrumbs(head), "ld_types": list(dict.fromkeys(t for n in nodes for t in _ld_type(n))),
        "app_name": _s(app.get("name")), "app_description": _s(app.get("description")),
        "app_category": _s(app.get("applicationCategory")), "offer_price": _dec(offer.get("price")),
        "offer_currency": cur if cur and re.fullmatch(r"[A-Z]{3}", cur) else None,
        "offer_price_raw": _s(offer.get("price")), "how_to_name": _s(howto.get("name")), "how_to_steps": steps,
        "faq": faq_from_ld(head), "seo": seo(head), "sitemap_lastmod": iso(body.get("sitemap_lastmod")),
        "source": env.provenance(),
    }
    if ptype != "room":
        e.update(body_fields(html, "html", sel, cut_boilerplate=True))
    return [e]


# ================================================================== promos (JSON APIs)

def parse_datetime_settings(env: Envelope, sel: Selection) -> list[dict]:
    out = []
    for it in _dicts(env.body):
        src = _s(it.get("source"))
        if not src:
            continue
        dt = it.get("datetimes") if isinstance(it.get("datetimes"), dict) else {}
        params = {k: v for k, v in (it.get("params") or {}).items() if v not in (None, "", [], {})} \
            if isinstance(it.get("params"), dict) else {}
        out.append({"kind": "site_promo_event", "event_id": src, "starts_at": iso(dt.get("starts_at")),
                    "ends_at": iso(dt.get("ends_at")), "params": params, "source": env.provenance()})
    return out


def parse_business_unlim(env: Envelope, sel: Selection) -> list[dict]:
    b = env.body if isinstance(env.body, dict) else {}
    out = []
    for period, cards in ((b.get("plan_cards") or {}).items() if isinstance(b.get("plan_cards"), dict) else []):
        for c in _dicts(cards):
            h = c.get("headline") if isinstance(c.get("headline"), dict) else {}
            bp = _s(c.get("billing_period")) or str(period)
            out.append({"kind": "site_business_unlim_offer",
                        "offer_id": make_id("plan_card", bp, c.get("plan_type")), "section": "plan_card",
                        "plan_type": _s(c.get("plan_type")), "billing_period": bp,
                        "duration_days": _int(c.get("duration_days") or h.get("duration_days")),
                        "model": _s(h.get("model")), "max_duration_seconds": _int(h.get("max_duration_seconds")),
                        "max_resolution": _s(h.get("max_resolution")),
                        "requires_business_verification": _bool(h.get("requires_business_verification")),
                        "models": _dicts(c.get("models")), "source": env.provenance()})
    banner = b.get("pricing_banner") if isinstance(b.get("pricing_banner"), dict) else {}
    for o in _dicts(banner.get("offers")):
        out.append({"kind": "site_business_unlim_offer",
                    "offer_id": make_id("pricing_banner", o.get("billing_period"), o.get("plan_type")),
                    "section": "pricing_banner", "plan_type": _s(o.get("plan_type")),
                    "billing_period": _s(o.get("billing_period")), "duration_days": _int(o.get("duration_days")),
                    "model": _s(o.get("model")), "max_duration_seconds": _int(o.get("max_duration_seconds")),
                    "max_resolution": _s(o.get("max_resolution")),
                    "requires_business_verification": _bool(banner.get("requires_business_verification")),
                    "models": [], "source": env.provenance()})
    return out


def parse_game_gift(env: Envelope, sel: Selection) -> list[dict]:
    b = env.body if isinstance(env.body, dict) else {}
    out = []
    for n in _dicts(b.get("networks")):
        net = _s(n.get("id"))
        for c in _dicts(n.get("countries")):
            code = _s(c.get("code"))
            if net and code:
                out.append({"kind": "site_game_gift", "gift_id": make_id("game_gift", net, code), "network": net,
                            "country_code": code, "fulfillment_mode": _s(c.get("fulfillment_mode")),
                            "amount_label": _s(c.get("amount_label")), "source": env.provenance()})
    return out


# ================================================================== community rooms (fnf-community API, opt-in)

def _room_url(slug: Any) -> str:
    return f"{SITE}/community/rooms/{slug}"


def parse_rooms_list(env: Envelope, sel: Selection) -> list[dict]:
    b = env.body if isinstance(env.body, dict) else {}
    off = _int(env.params.get("offset")) or 0
    out = []
    for n, r in enumerate(_dicts(b.get("items"))):
        if not r.get("id") or not r.get("slug"):
            continue
        wc = r.get("works_counts") if isinstance(r.get("works_counts"), dict) else {}
        cs = r.get("call_status") if isinstance(r.get("call_status"), dict) else {}
        au = r.get("author") if isinstance(r.get("author"), dict) else {}
        out.append({
            "kind": "site_room", "room_id": str(r["id"]), "slug": str(r["slug"]), "url": _room_url(r["slug"]),
            "name": _s(r.get("name")), "description": _s(r.get("description")), "avatar_url": _s(r.get("avatar_url")),
            "cover_url": _s(r.get("cover_url")), "works_count": _int(r.get("works_count")),
            "works_shots": _int(wc.get("shot")), "works_projects": _int(wc.get("project_publication")),
            "works_blog_posts": _int(wc.get("blog_post")), "followers_count": _int(r.get("followers_count")),
            "posts_count": None, "discussions_count": None, "call_status": _s(cs.get("status")),
            "call_participants": _int(cs.get("participant_count")), "owner_user_id": _s(au.get("user_id")),
            "owner_username": _s(au.get("username")) if sel.with_profiles else None, "pinned": _bool(r.get("pinned")),
            "members_can_post": _bool(r.get("members_can_post")), "join_approval": _bool(r.get("join_approval")),
            "project_publication_id": _s(r.get("project_publication_id")), "contest_id": _s(r.get("contest_id")),
            "original_space_id": _s(r.get("original_space_id")),
            "works_preview_ids": [str(w["item_id"]) for w in _dicts(r.get("works_preview")) if w.get("item_id")],
            "created_at": iso(r.get("created_at")), "position": off + n, "source": env.provenance()})
    return out


def parse_room_stats(env: Envelope, sel: Selection) -> list[dict]:
    """room-stats -> an aux record merged into site_room by build_dataset (not a collection of its own)."""
    b = env.body if isinstance(env.body, dict) else {}
    rid = env.params.get("room_id")
    if not rid:
        return []
    return [{"kind": "site_room_stats", "room_id": str(rid), "posts": _int(b.get("posts")),
             "discussions": _int(b.get("discussions"))}]


def parse_room_items(env: Envelope, sel: Selection) -> list[dict]:
    b = env.body if isinstance(env.body, dict) else {}
    rid, rslug = env.params.get("room_id") or "", env.params.get("room_slug")
    off = _int(env.params.get("offset")) or 0
    out = []
    for n, it in enumerate(_dicts(b.get("items"))):
        sid = it.get("space_item_id")
        x = it.get("item") if isinstance(it.get("item"), dict) else {}
        if not sid:
            continue
        t = str(it.get("item_type") or "unknown")
        t = t if t in ("shot", "project_publication", "blog_post") else "unknown"
        e: dict[str, Any] = {"kind": "site_room_item", "room_item_id": str(sid), "room_id": rid, "room_slug": rslug,
                             "item_type": t, "pinned": _bool(it.get("pinned")), "position": off + n,
                             "source": env.provenance()}
        cover = x.get("cover") if isinstance(x.get("cover"), dict) else {}
        if t == "shot":
            pub = x.get("publication") if isinstance(x.get("publication"), dict) else {}
            res = x.get("results") if isinstance(x.get("results"), dict) else {}
            raw = res.get("raw") if isinstance(res.get("raw"), dict) else {}
            mn = res.get("min") if isinstance(res.get("min"), dict) else {}
            params = x.get("params") if isinstance(x.get("params"), dict) else {}
            prompt = _s(params.get("prompt"))
            e.update({"item_id": _s(pub.get("id")), "generation_id": _s(x.get("id")),
                      "url": f"{SITE}/community/generations?shot={pub['id']}" if pub.get("id") else None,
                      "title": prompt[:200] if prompt else None, "prompt": prompt,
                      "job_set_type": _s(x.get("job_set_type")), "media_type": _s(raw.get("type") or mn.get("type")),
                      "media_url": _s(raw.get("url")), "thumbnail_url": _s(raw.get("thumbnail_url") or mn.get("url")),
                      "likes": _int(pub.get("likes_count")), "views": _int(pub.get("views_count")),
                      "author_user_ids": [str(x["user_id"])] if x.get("user_id") else [],
                      "created_at": iso(x.get("published_at") or x.get("created_at"))})
        elif t == "project_publication":
            e.update({"item_id": _s(x.get("publication_id")), "title": _s(x.get("name")), "slug": _s(x.get("slug")),
                      "description": _s(x.get("description")), "media_url": _s(cover.get("url")),
                      "thumbnail_url": _s(cover.get("thumbnail_url") or cover.get("min_url")),
                      "project_type": _s(x.get("type")), "duration_seconds": _float(x.get("duration_seconds")),
                      "likes": _int(x.get("likes")), "views": _int(x.get("views")), "comments": _int(x.get("comments")),
                      "tags": [str(v) for v in x.get("tags") or [] if v is not None],
                      "author_user_ids": [str(v) for v in x.get("author_user_ids") or [] if v],
                      "created_at": iso(x.get("created_at"))})
        elif t == "blog_post":
            au = x.get("author") if isinstance(x.get("author"), dict) else {}
            e.update({"item_id": _s(x.get("id")), "title": _s(x.get("title")), "slug": _s(x.get("slug")),
                      "description": _s(x.get("subtitle")), "media_url": _s(cover.get("url")),
                      "reading_time_minutes": _int(x.get("reading_time_minutes")),
                      "likes": _int(x.get("likes_count")), "views": _int(x.get("views_count")),
                      "tags": [str(v.get("name") if isinstance(v, dict) else v) for v in x.get("tags") or [] if v],
                      "author_user_ids": [str(au["id"])] if au.get("id") else [],
                      "created_at": iso(x.get("published_at") or x.get("created_at"))})
        out.append(e)
    return out


def parse_room_discussions(env: Envelope, sel: Selection) -> list[dict]:
    from ..community.parsers import parse_post
    b = env.body if isinstance(env.body, dict) else {}
    out = []
    for p in _dicts(b.get("publications")):
        if not p.get("id"):
            continue
        e = parse_post(p, sel, env.provenance())
        e["kind"] = "site_room_discussion"
        e["room_id"] = e.get("room_id") or env.params.get("room_id")
        e["room_slug"] = env.params.get("room_slug")
        out.append(e)
    return out


# ================================================================== sitemaps + dispatch

def sitemap_urls(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, dict) and "xml" in body:
        body = extract_sitemap(body["xml"])
    return list((body or {}).get("urls") or []) if isinstance(body, dict) else []


PARSERS = {
    "apps_index": parse_apps_index,
    "app_page": parse_app_page,
    "academy_index": parse_academy_index,
    "course_page": parse_course_page,
    "lesson_page": parse_lesson_page,
    "mcp_index": parse_mcp_index,
    "mcp_skill_page": parse_mcp_skill,
    "mcp_bundle_page": parse_mcp_bundle,
    "originals_index": parse_originals_index,
    "episode_page": parse_episode_page,
    "mixed_media_page": parse_mixed_media_page,
    "landing_page": parse_landing,
    "room_page": parse_landing,
    "datetime_settings": parse_datetime_settings,
    "business_unlim": parse_business_unlim,
    "game_gift": parse_game_gift,
    "rooms_api": parse_rooms_list,
    "room_stats": parse_room_stats,
    "room_items": parse_room_items,
    "room_discussions": parse_room_discussions,
}


def parse_envelope(env: Envelope, sel: Selection) -> list[dict]:
    if env.status != 200:
        return []
    fn = PARSERS.get(env.endpoint)
    return fn(env, sel) if fn else []               # sitemaps: discovery only


def keep(e: dict, sel: Selection) -> bool:
    """--only filters detail records by URL path (index/aux records are always kept)."""
    if e.get("kind") not in PRIMARY_KINDS or not sel.only:
        return True
    if e.get("kind") in ("site_room_item", "site_room_discussion"):     # filtered by their room's page path
        return sel.path_ok(f"/community/rooms/{e.get('room_slug') or ''}")
    return sel.path_ok(urlsplit(e.get("url") or "").path)


__all__ = ["parse_envelope", "keep", "sitemap_urls", "is_landing_path"]
