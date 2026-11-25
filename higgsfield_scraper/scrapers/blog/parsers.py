"""Pure parsers: Envelope -> entity dicts (each with "kind"). No network, no Scrapy.

Envelope bodies used by this scraper (the spider converts non-JSON responses before archiving them):

* JSON API lists (`talent_posts`, `recommended_posts`): the untouched API JSON.
* SSR pages (`blog_index`, `blog_page`, `blog_author`, `help_index`, `help_article`, `case_studies_index`,
  `case_study`, `changelog`, `enterprise_index`, `enterprise_article`):
      {"format": "tsr", "path": "/blog/x", "sitemap_lastmod": "...", "head": {...}, "matches": [...]}
  i.e. the TanStack router state decoded from the page (`$_TSR.router`) + a few <head> fields. A body of the form
  {"html": "<!DOCTYPE html>..."} (a saved page) is accepted too and converted on the fly (tests use this).
* Sitemaps (`*_sitemap`): {"format": "sitemap", "urls": [{"loc": ..., "lastmod": ...}]} or {"xml": "..."}.
* Community/talent post bodies (`post_content`): {"format": "yjs", "content_url": ..., "content_b64": "..."}.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterable, Optional
from xml.etree import ElementTree

from ...raw import Envelope
from .content import convert_html, convert_lexical, convert_markdown, markdown_to_text
from .endpoints import SITE
from .options import Selection
from .schemas import PRIMARY_KINDS
from .tsr import TsrParseError, router_matches
from .yjs import decode_lexical

# ================================================================== page extraction (also used by the spider)

_STRIP_WHEN_DETAIL = ("screen", "navigation")       # repeated listing data on detail pages (fetched once via indexes)


class _Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title: Optional[str] = None
        self.canonical: Optional[str] = None
        self.lang: Optional[str] = None
        self.ld: list[str] = []
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title" and self.title is None:
            self._in_title, self._buf = True, []
        elif tag == "meta":
            k = a.get("property") or a.get("name")
            if k and "content" in a and k not in self.meta:
                self.meta[k] = a["content"]
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld, self._buf = True, []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self.title, self._in_title = "".join(self._buf).strip(), False
        elif tag == "script" and self._in_ld:
            self.ld.append("".join(self._buf))
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title or self._in_ld:
            self._buf.append(data)


def _head(html: str) -> dict[str, Any]:
    end = html.find("$_TSR")
    p = _Head()
    try:
        p.feed(html[: end if end > 0 else 400_000])
    except Exception:  # pragma: no cover - malformed markup
        pass
    ld = []
    for s in p.ld:
        try:
            ld.append(json.loads(s))
        except ValueError:
            continue
    return {"title": p.title, "lang": p.lang, "canonical": p.canonical,
            "description": p.meta.get("description"), "og_title": p.meta.get("og:title"),
            "og_image": p.meta.get("og:image"), "og_type": p.meta.get("og:type"),
            "author": p.meta.get("author"), "ld_json": ld}


def _article_html(html: str) -> Optional[str]:
    for tag in ("article", "main"):
        i = html.find(f"<{tag}")
        if i >= 0:
            j = html.find(f"</{tag}>", i)
            if j > 0:
                return html[i:j + len(tag) + 3]
    return None


def extract_page(html: str, path: Optional[str] = None, lastmod: Optional[str] = None) -> dict[str, Any]:
    """Saved SSR page -> compact envelope body (router state + head). Raises nothing."""
    body: dict[str, Any] = {"format": "tsr", "path": path, "sitemap_lastmod": lastmod, "head": _head(html)}
    try:
        matches = router_matches(html)
    except (TsrParseError, IndexError, KeyError, ValueError) as e:
        matches = []
        body["tsr_error"] = f"{type(e).__name__}: {e}"[:300]
    out = []
    for m in matches:
        if not isinstance(m, dict) or m.get("l") is None:
            continue
        loader = m["l"]
        if isinstance(loader, dict) and ("entry" in loader or "article" in loader):
            loader = {k: v for k, v in loader.items() if k not in _STRIP_WHEN_DETAIL}
        out.append({"i": m.get("i"), "s": m.get("s"), "l": loader})
    body["matches"] = out
    if not out:                                     # fallback for pages without router state
        body["article_html"] = _article_html(html)
    return body


def extract_sitemap(xml: str) -> dict[str, Any]:
    urls = []
    try:
        root = ElementTree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except ElementTree.ParseError as e:
        return {"format": "sitemap", "urls": [], "error": str(e)}
    for u in root.iter():
        if u.tag.endswith("}url") or u.tag == "url":
            loc = lastmod = None
            for c in u:
                if c.tag.endswith("loc"):
                    loc = (c.text or "").strip()
                elif c.tag.endswith("lastmod"):
                    lastmod = (c.text or "").strip() or None
            if loc:
                urls.append({"loc": loc, "lastmod": lastmod})
    return {"format": "sitemap", "urls": urls}


def page_body(body: Any) -> dict[str, Any]:
    if isinstance(body, dict) and "html" in body and "matches" not in body:
        return extract_page(body["html"], body.get("path"), body.get("sitemap_lastmod"))
    return body if isinstance(body, dict) else {}


def sitemap_urls(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, dict) and "xml" in body:
        body = extract_sitemap(body["xml"])
    return list((body or {}).get("urls") or [])


def loader(body: dict, key: Optional[str] = None) -> Optional[dict]:
    """The innermost route's loader data (optionally the last one containing `key`)."""
    for m in reversed(body.get("matches") or []):
        l_ = m.get("l")
        if isinstance(l_, dict) and (key is None or key in l_):
            return l_
    return None


# ================================================================== small helpers

def iso(v: Any) -> Optional[str]:
    """ISO string / epoch seconds -> ISO-8601 UTC string (None if unparseable)."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
    s = str(v).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).isoformat()
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def minutes(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v))
    return int(m.group(0)) if m else None


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v: Any) -> Optional[int]:
    try:
        return None if v in (None, "") else int(v)
    except (TypeError, ValueError):
        return None


def _abs_url(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    return u if u.startswith("http") else SITE + (u if u.startswith("/") else "/" + u)


def category(c: Any) -> Optional[dict]:
    if not isinstance(c, dict):
        return None
    return {"id": _s(c.get("id")), "slug": _s(c.get("slug")), "title": _s(c.get("title")),
            "description": _s(c.get("description")), "icon": _s(c.get("icon")), "order": _int(c.get("order"))}


def author_ref(a: Any) -> Optional[dict]:
    if not isinstance(a, dict):
        return None
    return {"id": _s(a.get("id")), "slug": _s(a.get("slug")), "name": _s(a.get("fullName") or a.get("name")),
            "position": _s(a.get("position"))}


def cta(c: Any) -> Optional[dict]:
    if not isinstance(c, dict):
        return None
    return {"title": _s(c.get("title")), "description": _s(c.get("description")), "text": _s(c.get("ctaText")),
            "link": _s(c.get("ctaLink"))}


def faq(section: Any) -> list[dict]:
    items = (section or {}).get("items") if isinstance(section, dict) else None
    out = []
    for it in items or []:
        q = _s(it.get("title"))
        if not q:
            continue
        html = it.get("content")
        is_html = (it.get("contentType") or "HTML").upper() == "HTML"
        out.append({"question": q, "answer_html": html if is_html else None,
                    "answer_text": (convert_html(html)["content_text"] if is_html else _s(html))})
    return out


def related(posts: Any, base: str = "/blog/") -> list[dict]:
    out = []
    for p in posts or []:
        if not isinstance(p, dict):
            continue
        href = p.get("href") or ((p.get("banner") or {}).get("link")) or (base + p["slug"] if p.get("slug") else None)
        cat = p.get("category") or {}
        out.append({"id": _s(p.get("id")), "slug": _s(p.get("slug")), "title": _s(p.get("title")),
                    "url": _abs_url(href), "category_slug": _s(cat.get("slug")) if isinstance(cat, dict) else None,
                    "published_at": iso(p.get("seoPublishDateISO") or p.get("dateModified"))})
    return out


def headings_from_cms(hs: Any) -> Optional[list[dict]]:
    if not hs:
        return None
    return [{"level": int(h.get("level") or 2), "text": _s(h.get("title")) or "", "anchor": _s(h.get("id"))}
            for h in hs if isinstance(h, dict) and _s(h.get("title"))]


def body_fields(sel: Selection, *, html: Optional[str] = None, markdown: Optional[str] = None,
                lexical: Optional[dict] = None, cms_headings: Any = None) -> dict[str, Any]:
    if not sel.with_content:
        return {}
    if lexical is not None:
        r = convert_lexical(lexical)
        r["content_blocks"] = lexical.get("children") or []
    elif markdown:
        r = convert_markdown(markdown, html)
        r["content_html"] = html
    elif html:
        r = convert_html(html)
        r["content_html"] = html
    else:
        return {}
    hs = headings_from_cms(cms_headings)
    if hs:
        r["headings"] = hs
    return r


def _extra(d: dict, used: Iterable[str]) -> dict[str, Any]:
    used = set(used)
    return {k: v for k, v in d.items() if k not in used and v not in (None, "", [], {})}


def _locale_of(path: Optional[str]) -> str:
    m = re.match(r"^/(es|ja|ko|de)(/|$)", path or "")
    return m.group(1) if m else "en"


def _breadcrumbs(head: dict) -> list[str]:
    for g in head.get("ld_json") or []:
        for node in (g.get("@graph") if isinstance(g, dict) and "@graph" in g else [g]):
            if isinstance(node, dict) and node.get("@type") == "BreadcrumbList":
                return [str(i.get("name")) for i in node.get("itemListElement") or [] if i.get("name")]
    return []


def _ld_dates(head: dict) -> tuple[Optional[str], Optional[str]]:
    for g in head.get("ld_json") or []:
        for node in (g.get("@graph") if isinstance(g, dict) and "@graph" in g else [g]):
            if isinstance(node, dict) and node.get("datePublished"):
                return iso(node.get("datePublished")), iso(node.get("dateModified"))
    return None, None


# ================================================================== blog posts / authors

POST_USED = ("id", "title", "breadcrumbTitle", "slug", "description", "seoDescription", "content", "mainBannerUrl",
             "author", "category", "cta", "hero", "headings", "relatedPosts", "readingTime", "dateCreated",
             "dateModified", "publishDate", "seoPublishDateISO", "aboutSection", "faqSection", "banner", "cardUrl")


def blog_post(p: dict, env: Envelope, sel: Selection, *, path: str, head: Optional[dict] = None,
              lastmod: Optional[str] = None, localization: Optional[dict] = None,
              record_source: str = "page") -> dict:
    head = head or {}
    hero = p.get("hero") or {}
    media = hero.get("media") or {}
    banner = p.get("banner") or {}
    cat = category(p.get("category"))
    ld_pub, ld_mod = _ld_dates(head)
    sub = _s(hero.get("description")) or _s(banner.get("description"))
    slug = p.get("slug") or path.rstrip("/").rsplit("/", 1)[-1]
    e = {
        "kind": "blog_post", "post_id": str(p.get("id") or slug), "slug": slug, "url": SITE + path,
        "locale": _locale_of(path), "title": _s(p.get("title")) or _s(banner.get("title")),
        "breadcrumb_title": _s(p.get("breadcrumbTitle")), "subtitle": sub, "description": _s(p.get("description")),
        "seo_description": _s(p.get("seoDescription")), "category": cat,
        "tags": [cat["slug"]] if cat and cat.get("slug") else [], "author": author_ref(p.get("author")),
        "cover_url": _s(p.get("mainBannerUrl")) or _s(p.get("cardUrl")), "card_url": _s(p.get("cardUrl")),
        "banner_image_url": _s(banner.get("bannerImage")), "hero_media_url": _s(media.get("source")),
        "hero_media_type": _s(media.get("type")), "hero_media_width": _int(media.get("width")),
        "hero_media_height": _int(media.get("height")), "cta": cta(p.get("cta")),
        "reading_time": _s(p.get("readingTime")), "reading_time_minutes": minutes(p.get("readingTime")),
        "published_at": iso(p.get("seoPublishDateISO")) or ld_pub, "created_at": iso(p.get("dateCreated")),
        "updated_at": iso(p.get("dateModified")) or ld_mod, "publish_date_label": _s(p.get("publishDate")),
        "related_posts": related(p.get("relatedPosts")), "faq": faq(p.get("faqSection")),
        "about": p.get("aboutSection") or None,
        "localization_status": (localization or {}).get("status") if isinstance(localization, dict) else None,
        "sitemap_lastmod": lastmod, "page_title": head.get("title"), "record_source": record_source,
        "extra": _extra(p, POST_USED), "source": env.provenance(),
    }
    if record_source == "page":
        e.update(body_fields(sel, html=p.get("content"), cms_headings=p.get("headings")))
    return e


def parse_blog_index(env: Envelope, sel: Selection) -> list[dict]:
    if sel.with_content:
        return []                                   # discovery only; every post comes from its own page
    body = page_body(env.body)
    l_ = loader(body, "categoryAndPosts") or {}
    out, seen = [], set()
    groups = list(l_.get("categoryAndPosts") or [])
    for p in [l_.get("mainPost")] + list(l_.get("featuredPosts") or []) + [p for g in groups for p in g.get("posts") or []]:
        if not isinstance(p, dict) or not p.get("slug") or p["slug"] in seen:
            continue
        seen.add(p["slug"])
        prefix = "" if (body.get("path") or "/blog").startswith("/blog") else body["path"].split("/blog")[0]
        out.append(blog_post(p, env, sel, path=f"{prefix}/blog/{p['slug']}", record_source="index"))
    return out


def index_post_slugs(body: Any) -> tuple[list[str], list[str]]:
    """(post slugs, category slugs) listed on /blog."""
    l_ = loader(page_body(body), "categoryAndPosts") or {}
    posts, cats = [], []
    for g in l_.get("categoryAndPosts") or []:
        c = (g.get("category") or {}).get("slug")
        if c:
            cats.append(c)
        posts += [p["slug"] for p in g.get("posts") or [] if p.get("slug")]
    for p in [l_.get("mainPost")] + list(l_.get("featuredPosts") or []):
        if isinstance(p, dict) and p.get("slug"):
            posts.append(p["slug"])
    return list(dict.fromkeys(posts)), list(dict.fromkeys(cats))


def parse_blog_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    path = body.get("path") or env.params.get("path") or ""
    l_ = loader(body, "entry")
    if l_ is None:
        return _fallback_post(env, sel, body, path)
    entry = l_.get("entry") or {}
    if entry.get("type") != "post" or not isinstance(entry.get("post"), dict):
        return []                                   # category listing pages (/blog/guides, ...)
    return [blog_post(entry["post"], env, sel, path=path, head=body.get("head"),
                      lastmod=body.get("sitemap_lastmod"), localization=entry.get("cmsLocalization"))]


def _fallback_post(env: Envelope, sel: Selection, body: dict, path: str) -> list[dict]:
    """No router state: build the post from <head> + the <article> HTML."""
    head = body.get("head") or {}
    art = body.get("article_html")
    if not art and not head.get("title"):
        return []
    slug = path.rstrip("/").rsplit("/", 1)[-1]
    pub, mod = _ld_dates(head)
    p = {"id": slug, "slug": slug, "title": head.get("og_title") or head.get("title"),
         "seoDescription": head.get("description"), "mainBannerUrl": head.get("og_image")}
    e = blog_post(p, env, sel, path=path, head=head, lastmod=body.get("sitemap_lastmod"), record_source="page")
    e["published_at"], e["updated_at"] = pub, mod
    e.update(body_fields(sel, html=art))
    e["extra"] = {"parsed_from": "html_fallback"}
    return [e]


def parse_author_page(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    path = body.get("path") or env.params.get("path") or ""
    l_ = loader(body, "screen") or {}
    scr = l_.get("screen") or {}
    a = scr.get("author")
    if not isinstance(a, dict):
        return []
    posts = [p for p in scr.get("posts") or [] if isinstance(p, dict)]
    return [{
        "kind": "blog_author", "slug": a.get("slug") or path.rsplit("/", 1)[-1], "author_id": _s(a.get("id")),
        "name": _s(a.get("fullName")), "position": _s(a.get("position")), "description": _s(a.get("description")),
        "photo_url": _s(a.get("photoUrl")), "linkedin_url": _s(a.get("hrefLinkedin")), "url": SITE + path,
        "post_count": len(posts), "post_slugs": [p["slug"] for p in posts if p.get("slug")], "record_source": "page",
        "extra": _extra(a, ("id", "slug", "fullName", "position", "description", "photoUrl", "hrefLinkedin")),
        "source": env.provenance(),
    }]


# ================================================================== help centers

HELP_USED = ("category", "dateModified", "description", "id", "order", "searchKeywords", "slug", "title", "author",
             "content", "dateCreated", "faqSection", "headings", "markdown", "readingTime", "relatedPosts",
             "relatedArticles", "seoDescription", "seoTitle", "cardTitle", "cardImageUrl", "lastUpdated")


def help_article(a: dict, env: Envelope, sel: Selection, *, section: str, path: str, wrapper: Optional[dict] = None,
                 head: Optional[dict] = None, lastmod: Optional[str] = None, record_source: str = "page") -> dict:
    wrapper = wrapper or {}
    head = head or {}
    cat = category(a.get("category"))
    loc = wrapper.get("cmsLocalization")
    rel_base = "/creator-hub/help-center/" if section == "creator-hub" else "/enterprise-help-center/"
    rel = []
    for r in a.get("relatedPosts") or a.get("relatedArticles") or []:
        rc = (r.get("category") or {}).get("slug") if isinstance(r, dict) else None
        rel += [{**x, "url": _abs_url(f"{rel_base}{rc}/{x['slug']}") if rc and x.get("slug") else x["url"]}
                for x in related([r], base=rel_base)]
    e = {
        "kind": "blog_help_article", "article_id": str(a.get("id") or f"{section}:{path}"), "section": section,
        "slug": a.get("slug") or path.rstrip("/").rsplit("/", 1)[-1], "url": SITE + path, "locale": _locale_of(path),
        "category_slug": (cat or {}).get("slug") or (path.strip("/").split("/")[-2] if path.count("/") >= 3 else None),
        "category": cat, "title": _s(a.get("title")), "card_title": _s(a.get("cardTitle")),
        "description": _s(a.get("description")), "seo_title": _s(a.get("seoTitle")),
        "seo_description": _s(a.get("seoDescription")),
        "search_keywords": [str(k) for k in a.get("searchKeywords") or [] if k], "order": _int(a.get("order")),
        "author": author_ref(a.get("author")), "card_image_url": _s(a.get("cardImageUrl")),
        "reading_time": _s(a.get("readingTime")), "reading_time_minutes": minutes(a.get("readingTime")),
        "created_at": iso(a.get("dateCreated")), "updated_at": iso(a.get("dateModified") or a.get("lastUpdated")),
        "faq": faq(a.get("faqSection")), "related_articles": rel,
        "previous_slug": _s((wrapper.get("previousArticle") or {}).get("slug")),
        "next_slug": _s((wrapper.get("nextArticle") or {}).get("slug")),
        "markdown_url": _s(wrapper.get("markdownLink")), "content_language": _s(wrapper.get("contentLanguage")),
        "localization_status": loc.get("status") if isinstance(loc, dict) else None,
        "breadcrumbs": _breadcrumbs(head), "sitemap_lastmod": lastmod, "page_title": head.get("title"),
        "record_source": record_source, "extra": _extra(a, HELP_USED), "source": env.provenance(),
    }
    if record_source == "page":
        e.update(body_fields(sel, html=a.get("content"), markdown=a.get("markdown"), cms_headings=a.get("headings")))
    return e


def parse_help_article(env: Envelope, sel: Selection, section: str) -> list[dict]:
    body = page_body(env.body)
    path = body.get("path") or env.params.get("path") or ""
    l_ = loader(body, "article")
    if not l_ or not isinstance(l_.get("article"), dict):
        return []
    return [help_article(l_["article"], env, sel, section=section, path=path, wrapper=l_, head=body.get("head"),
                         lastmod=body.get("sitemap_lastmod"))]


def help_index_paths(body: Any) -> list[str]:
    l_ = loader(page_body(body), "navigation") or {}
    out = []
    for g in (l_.get("navigation") or {}).get("groups") or []:
        for a in g.get("articles") or []:
            c = (a.get("category") or {}).get("slug") or (g.get("category") or {}).get("slug")
            if c and a.get("slug"):
                out.append(f"/creator-hub/help-center/{c}/{a['slug']}")
    return list(dict.fromkeys(out))


def parse_help_index(env: Envelope, sel: Selection) -> list[dict]:
    if sel.with_content:
        return []
    body = page_body(env.body)
    l_ = loader(body, "navigation") or {}
    out = []
    for g in (l_.get("navigation") or {}).get("groups") or []:
        for a in g.get("articles") or []:
            c = (a.get("category") or {}).get("slug") or (g.get("category") or {}).get("slug")
            if not a.get("slug"):
                continue
            out.append(help_article(a, env, sel, section="creator-hub",
                                    path=f"/creator-hub/help-center/{c}/{a['slug']}", record_source="index"))
    return out


def enterprise_index_paths(body: Any) -> list[str]:
    l_ = loader(page_body(body), "items") or {}
    return [i["path"] for i in l_.get("items") or [] if isinstance(i, dict) and i.get("path")
            and i["path"].strip("/").count("/") == 2]


def parse_enterprise_index(env: Envelope, sel: Selection) -> list[dict]:
    if sel.with_content:
        return []
    body = page_body(env.body)
    l_ = loader(body, "items") or {}
    out = []
    for it in l_.get("items") or []:
        p = it.get("path") or ""
        if p.strip("/").count("/") != 2:
            continue
        a = {"id": f"enterprise:{p}", "slug": p.rstrip("/").rsplit("/", 1)[-1], "title": it.get("name")}
        e = help_article(a, env, sel, section="enterprise", path=p, record_source="index")
        e["category_slug"] = p.strip("/").split("/")[1]
        out.append(e)
    return out


# ================================================================== case studies

CASE_USED = POST_USED + ("heroMetrics", "toolsUsed", "sidebarCta")


def case_study(p: dict, env: Envelope, sel: Selection, *, path: str, head: Optional[dict] = None,
               lastmod: Optional[str] = None, record_source: str = "page") -> dict:
    head = head or {}
    hero = p.get("hero") or {}
    media = hero.get("media") or {}
    banner = p.get("banner") or {}
    about = p.get("aboutSection") or {}
    slug = p.get("slug") or path.rstrip("/").rsplit("/", 1)[-1]
    e = {
        "kind": "blog_case_study", "case_study_id": str(p.get("id") or slug), "slug": slug, "url": SITE + path,
        "locale": _locale_of(path), "title": _s(p.get("title")) or _s(banner.get("title")),
        "breadcrumb_title": _s(p.get("breadcrumbTitle")),
        "subtitle": _s(hero.get("description")) or _s(banner.get("description")),
        "description": _s(p.get("description")), "seo_description": _s(p.get("seoDescription")),
        "category": category(p.get("category")), "author": author_ref(p.get("author")),
        "cover_url": _s(p.get("mainBannerUrl")) or _s(p.get("cardUrl")), "card_url": _s(p.get("cardUrl")),
        "banner_image_url": _s(banner.get("bannerImage")), "hero_media_url": _s(media.get("source")),
        "hero_media_type": _s(media.get("type")), "cta": cta(p.get("cta")),
        "hero_metrics": [{"label": _s(m.get("label")), "value": _s(m.get("value"))}
                         for m in p.get("heroMetrics") or [] if isinstance(m, dict)],
        "tools_used": [{"name": _s(t.get("name")), "slug": _s(t.get("slug")), "icon_url": _s(t.get("iconUrl"))}
                       for t in p.get("toolsUsed") or [] if isinstance(t, dict)],
        "about_title": _s(about.get("title")), "about_intro": _s(about.get("intro")),
        "about_facts": list(about.get("facts") or []),
        "reading_time": _s(p.get("readingTime")), "reading_time_minutes": minutes(p.get("readingTime")),
        "published_at": iso(p.get("seoPublishDateISO")), "created_at": iso(p.get("dateCreated")),
        "updated_at": iso(p.get("dateModified")),
        "related_posts": related(p.get("relatedPosts"), base="/creator-hub/case-studies/"),
        "faq": faq(p.get("faqSection")), "sitemap_lastmod": lastmod, "page_title": head.get("title"),
        "record_source": record_source,
        "extra": _extra({**p, **({"sidebarCta": p["sidebarCta"]} if p.get("sidebarCta") else {})},
                        CASE_USED) | ({"sidebar_cta": p["sidebarCta"]} if p.get("sidebarCta") else {}),
        "source": env.provenance(),
    }
    if record_source == "page":
        e.update(body_fields(sel, html=p.get("content"), cms_headings=p.get("headings")))
    return e


def parse_case_study(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    path = body.get("path") or env.params.get("path") or ""
    l_ = loader(body, "entry")
    entry = (l_ or {}).get("entry") or {}
    if entry.get("type") != "post" or not isinstance(entry.get("post"), dict):
        return []
    return [case_study(entry["post"], env, sel, path=path, head=body.get("head"), lastmod=body.get("sitemap_lastmod"))]


def case_study_slugs(body: Any) -> tuple[list[str], list[str]]:
    l_ = loader(page_body(body), "categories") or {}
    slugs, cats = [], []
    f = l_.get("featuredCaseStudy")
    if isinstance(f, dict) and f.get("slug"):
        slugs.append(f["slug"])
    for g in l_.get("categories") or []:
        if (g.get("category") or {}).get("slug"):
            cats.append(g["category"]["slug"])
        slugs += [p["slug"] for p in g.get("posts") or [] if p.get("slug")]
    return list(dict.fromkeys(slugs)), cats


def parse_case_studies_index(env: Envelope, sel: Selection) -> list[dict]:
    if sel.with_content:
        return []
    body = page_body(env.body)
    l_ = loader(body, "categories") or {}
    posts = [l_.get("featuredCaseStudy")] + [p for g in l_.get("categories") or [] for p in g.get("posts") or []]
    out, seen = [], set()
    for p in posts:
        if isinstance(p, dict) and p.get("slug") and p["slug"] not in seen:
            seen.add(p["slug"])
            out.append(case_study(p, env, sel, path=f"/creator-hub/case-studies/{p['slug']}", record_source="index"))
    return out


# ================================================================== changelog

def parse_changelog(env: Envelope, sel: Selection) -> list[dict]:
    body = page_body(env.body)
    path = body.get("path") or "/creator-hub/changelog"
    l_ = loader(body, "entries") or {}
    out = []
    for en in l_.get("entries") or []:
        if not isinstance(en, dict) or not en.get("id"):
            continue
        cat = category(en.get("category"))
        e = {
            "kind": "blog_changelog_entry", "entry_id": str(en["id"]), "anchor": _s(en.get("anchor")),
            "url": SITE + path + (f"#{en['anchor']}" if en.get("anchor") else ""), "title": _s(en.get("title")),
            "summary": _s(en.get("summary")), "category": cat, "category_slug": (cat or {}).get("slug"),
            "chips": [{"id": _s(c.get("id")), "slug": _s(c.get("slug")), "title": _s(c.get("title"))}
                      for c in en.get("chips") or [] if isinstance(c, dict)],
            "search_keywords": [str(k) for k in en.get("searchKeywords") or [] if k],
            "released_at": iso(en.get("releaseDate")), "updated_at": iso(en.get("dateModified")),
            "extra": _extra(en, ("id", "anchor", "title", "summary", "content", "releaseDate", "dateModified",
                                 "searchKeywords", "category", "chips")),
            "source": env.provenance(),
        }
        e.update(body_fields(sel, html=en.get("content")))
        out.append(e)
    return out


# ================================================================== community / talent posts (JSON API + Yjs)

USER_USED = ("id", "state", "title", "subtitle", "slug", "cover", "tags", "related_posts", "reading_time",
             "reading_time_minutes", "breadcrumb_label", "pinned_position", "likes_count", "views_count",
             "liked_by_me", "folder_id", "content_url", "draft", "published_at", "created_at", "updated_at",
             "author", "review_state", "flagged_media")


def user_post(it: dict, env: Envelope, sel: Selection, feed: str) -> dict:
    a = it.get("author") or {}
    cov = it.get("cover") or None
    username = a.get("username")
    return {
        "kind": "blog_talent_post" if feed == "talents" else "blog_community_post",
        "post_id": str(it["id"]), "feed": feed, "slug": _s(it.get("slug")),
        "url": f"{SITE}/@{username}/blogs/{it['slug']}" if username and it.get("slug") else None,
        "state": _s(it.get("state")), "title": _s(it.get("title")), "subtitle": _s(it.get("subtitle")),
        "tags": [str(t.get("slug") or t.get("name") or t) if isinstance(t, dict) else str(t)
                 for t in it.get("tags") or []],
        "cover": {"id": _s(cov.get("id")), "url": _s(cov.get("url")), "type": _s(cov.get("type")),
                  "width": _int(cov.get("width")), "height": _int(cov.get("height"))} if isinstance(cov, dict) else None,
        "author": {"user_id": _s(a.get("id")), "username": _s(username),
                   "avatar_url": _s(a.get("avatar_url")) if sel.include_author_avatars else None} if a else None,
        "reading_time": _s(it.get("reading_time")), "reading_time_minutes": _int(it.get("reading_time_minutes")),
        "likes_count": _int(it.get("likes_count")), "views_count": _int(it.get("views_count")),
        "breadcrumb_label": _s(it.get("breadcrumb_label")), "pinned_position": _int(it.get("pinned_position")),
        "folder_id": _s(it.get("folder_id")), "content_url": _s(it.get("content_url")),
        "related_posts": list(it.get("related_posts") or []), "review_state": _s(it.get("review_state")),
        "flagged_media": it.get("flagged_media"), "published_at": iso(it.get("published_at")),
        "created_at": iso(it.get("created_at")), "updated_at": iso(it.get("updated_at")),
        "content_status": "not_fetched",
        "extra": _extra(it, USER_USED) | ({"draft": it["draft"]} if it.get("draft") else {})
        | ({"liked_by_me": it["liked_by_me"]} if it.get("liked_by_me") is not None else {}),
        "source": env.provenance(),
    }


def parse_user_posts(env: Envelope, sel: Selection, feed: str) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    return [user_post(it, env, sel, feed) for it in body.get("items") or [] if isinstance(it, dict) and it.get("id")]


def parse_post_content(env: Envelope, sel: Selection) -> list[dict]:
    body = env.body if isinstance(env.body, dict) else {}
    pid = env.params.get("post_id") or body.get("post_id")
    if not pid:
        return []
    e: dict[str, Any] = {"kind": "blog_post_content", "post_id": pid, "content_url": body.get("content_url") or env.url,
                         "source": env.provenance()}
    try:
        data = base64.b64decode(body.get("content_b64") or "")
        e["content_bytes"] = len(data)
        tree = decode_lexical(data)
        e.update(body_fields(Selection(what=sel.what, with_content=True), lexical=tree or {"children": []}))
        e["content_status"] = "ok" if tree else "empty"
    except Exception as ex:  # corrupt / unknown binary: keep the post, flag the body
        e["content_status"] = f"error: {type(ex).__name__}: {ex}"[:200]
    return [e]


# ================================================================== dispatch + filters

def parse_envelope(env: Envelope, sel: Selection) -> list[dict]:
    if env.status != 200:
        return []
    ep = env.endpoint
    if ep == "blog_index":
        return parse_blog_index(env, sel)
    if ep == "blog_page":
        return parse_blog_page(env, sel)
    if ep == "blog_author":
        return parse_author_page(env, sel)
    if ep == "help_index":
        return parse_help_index(env, sel)
    if ep == "help_article":
        return parse_help_article(env, sel, "creator-hub")
    if ep == "enterprise_index":
        return parse_enterprise_index(env, sel)
    if ep == "enterprise_article":
        return parse_help_article(env, sel, "enterprise")
    if ep == "case_studies_index":
        return parse_case_studies_index(env, sel)
    if ep == "case_study":
        return parse_case_study(env, sel)
    if ep == "changelog":
        return parse_changelog(env, sel)
    if ep == "talent_posts":
        return parse_user_posts(env, sel, "talents")
    if ep == "recommended_posts":
        return parse_user_posts(env, sel, "community")
    if ep == "post_content":
        return parse_post_content(env, sel)
    return []                                       # sitemaps etc.: discovery only


def _date_of(e: dict) -> Optional[str]:
    for k in ("published_at", "released_at", "updated_at", "created_at"):
        if e.get(k):
            return str(e[k])[:10]
    return None


def _tags_of(e: dict) -> set[str]:
    out = {str(t).lower() for t in e.get("tags") or []}
    for c in (e.get("category"),):
        if isinstance(c, dict):
            out |= {str(c[k]).lower() for k in ("slug", "title") if c.get(k)}
    if e.get("category_slug"):
        out.add(str(e["category_slug"]).lower())
    out |= {str(c.get("slug")).lower() for c in e.get("chips") or [] if c.get("slug")}
    return out


def keep(e: dict, sel: Selection) -> bool:
    if e.get("kind") not in PRIMARY_KINDS:
        return True
    if sel.tags and not (_tags_of(e) & set(sel.tags)):
        return False
    if sel.since:
        d = _date_of(e)
        if d is not None and d < sel.since:
            return False
    return True


__all__ = ["parse_envelope", "keep", "extract_page", "extract_sitemap", "markdown_to_text"]
