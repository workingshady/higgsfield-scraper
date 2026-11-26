"""Generate README assets (dark + light banner, architecture diagram, scrapers overview) in a Higgsfield-inspired palette.

Palette taken from higgsfield.ai's own CSS (theme-color #0f1113, signature lime #d1fe17, tertiary cyan #9ce6f3,
pink #ff005b, IBM Plex Mono). The banner says "UNOFFICIAL" and uses no Higgsfield logo or wordmark.

    python scripts/make_assets.py      ->  docs/assets/banner-dark.svg, banner-light.svg, architecture.svg, scrapers.svg
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets"

THEMES = {
    "dark": dict(bg="#0f1113", surface="#16181b", line="#2a2d31", grid="#ffffff", grid_op="0.04", text="#ffffff",
                 sub="#a7adb5", muted="#6e757e", lime="#d1fe17", lime_text="#d1fe17", lime_ink="#0f1113",
                 cyan="#9ce6f3", pink="#ff005b", pill_bg="#16181b", glow_op="0.18"),
    "light": dict(bg="#f5f6f1", surface="#ffffff", line="#dfe2da", grid="#0f1113", grid_op="0.05", text="#0f1113",
                  sub="#4a5058", muted="#7b828b", lime="#d1fe17", lime_text="#5f7311", lime_ink="#0f1113",
                  cyan="#1f8fa3", pink="#d6004c", pill_bg="#ffffff", glow_op="0.35"),
}
SANS = "Inter, 'Helvetica Neue', 'Segoe UI', Arial, sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

SCRAPERS = ["pricing", "community", "catalog", "projects", "blog", "site", "showcase", "studios", "models", "account"]
PILL_FONT, PILL_GAP = 13, 8            # each pill row must end before the flow nodes (x = 820)
PILL_ROWS = (SCRAPERS[:5], SCRAPERS[5:])   # 10 pills do not fit one row at 13 px: two rows of five


def pill_width(name: str) -> int:
    return round(len(name) * PILL_FONT * 0.62) + 24     # monospace advance ~0.6 em + padding


def banner(t: dict) -> str:
    pills = []
    for r, row in enumerate(PILL_ROWS):
        x, y = 64, 200 + r * 38
        for name in row:
            w = pill_width(name)
            first = name == SCRAPERS[0]
            pills.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="30" rx="15" fill="{t["lime"] if first else t["pill_bg"]}" '
                f'stroke="{t["lime"] if first else t["line"]}" stroke-width="1.5"/>'
                f'<text x="{x + w / 2}" y="{y + 19.5}" text-anchor="middle" font-family="{MONO}" font-size="{PILL_FONT}" font-weight="600" '
                f'fill="{t["lime_ink"] if first else t["text"]}">{name}</text>')
            x += w + PILL_GAP
        assert x - PILL_GAP <= 800, f"pills end at {x - PILL_GAP}, overlapping the flow nodes at 820"
    nodes = [("/plans", 64), ("/job-sets/costs", 118), ("/publications", 172)]
    flow = "".join(
        f'<rect x="820" y="{y}" width="150" height="30" rx="8" fill="{t["surface"]}" stroke="{t["line"]}"/>'
        f'<text x="895" y="{y + 20}" text-anchor="middle" font-family="{MONO}" font-size="13" fill="{t["sub"]}">{n}</text>'
        f'<path d="M970 {y + 15} C 1020 {y + 15}, 1030 133, 1068 133" fill="none" stroke="{t["lime_text"]}" stroke-width="2" '
        f'stroke-opacity="0.85"/>' for n, y in nodes)
    outs = "".join(
        f'<path d="M1100 133 C 1130 133, 1140 {y + 15}, 1170 {y + 15}" fill="none" stroke="{t["cyan"]}" stroke-width="2"/>'
        f'<rect x="1170" y="{y}" width="70" height="30" rx="8" fill="{t["surface"]}" stroke="{t["cyan"]}"/>'
        f'<text x="1205" y="{y + 20}" text-anchor="middle" font-family="{MONO}" font-size="13" fill="{t["text"]}">{n}</text>'
        for n, y in [("JSON", 64), ("CSV", 118), ("HAR", 172)])
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="320" viewBox="0 0 1280 320" role="img" aria-labelledby="title desc">
  <title id="title">higgsfield-scraper (unofficial)</title>
  <desc id="desc">Unofficial, reverse-engineered Scrapy scrapers for public Higgsfield.ai data, 10 scrapers: pricing, community, catalog, projects, blog, site (apps, academy, MCP), showcase, studios (marketplaces, studio galleries), models (JS model registry), account; cost estimates, export to datasets, cross-run dedupe, interactive menu.</desc>
  <defs>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse">
      <path d="M32 0H0V32" fill="none" stroke="{t["grid"]}" stroke-opacity="{t["grid_op"]}" stroke-width="1"/>
    </pattern>
    <radialGradient id="glow" cx="0.86" cy="0.42" r="0.45">
      <stop offset="0" stop-color="{t["lime"]}" stop-opacity="{t["glow_op"]}"/>
      <stop offset="1" stop-color="{t["lime"]}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1280" height="320" rx="20" fill="{t["bg"]}"/>
  <rect width="1280" height="320" rx="20" fill="url(#grid)"/>
  <rect width="1280" height="320" rx="20" fill="url(#glow)"/>
  <rect x="0.75" y="0.75" width="1278.5" height="318.5" rx="19.5" fill="none" stroke="{t["line"]}" stroke-width="1.5"/>

  <rect x="64" y="44" width="118" height="26" rx="13" fill="none" stroke="{t["pink"]}" stroke-width="1.5"/>
  <text x="123" y="62" text-anchor="middle" font-family="{MONO}" font-size="12" font-weight="600" letter-spacing="1.5" fill="{t["pink"]}">UNOFFICIAL</text>
  <text x="196" y="62" font-family="{MONO}" font-size="12" letter-spacing="1" fill="{t["muted"]}">REVERSE-ENGINEERED · SCRAPY · PYDANTIC</text>

  <text x="62" y="132" font-family="{SANS}" font-size="66" font-weight="800" letter-spacing="-2" fill="{t["text"]}">higgsfield<tspan fill="{t["lime_text"]}">-scraper</tspan></text>
  <text x="64" y="172" font-family="{SANS}" font-size="22" fill="{t["sub"]}">Every public Higgsfield.ai dataset — validated, organized, exported.</text>
  <rect x="64" y="184" width="64" height="4" rx="2" fill="{t["lime"]}"/>
  {"".join(pills)}
  <text x="64" y="298" font-family="{MONO}" font-size="14" fill="{t["muted"]}"><tspan fill="{t["lime_text"]}">$</tspan> python -m higgsfield_scraper menu<tspan dx="18" fill="{t["muted"]}"># or: scrape &lt;scraper&gt; · export · diff</tspan></text>

  {flow}
  <circle cx="1084" cy="133" r="17" fill="{t["lime"]}"/>
  <path d="M1076 133 l6 6 l11 -12" fill="none" stroke="{t["lime_ink"]}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
  {outs}
  <text x="1084" y="236" text-anchor="middle" font-family="{MONO}" font-size="12" fill="{t["muted"]}">validate · dedup · export</text>
</svg>
'''


def architecture() -> str:
    """Container-level view of one run, following diagram best practice: title with type+scope, swim lanes
    (trust boundaries), numbered events, labelled arrows that start/end on box edges, consistent line semantics,
    and a legend that explains every colour, line style and border."""
    t = THEMES["dark"]
    W, H = 1280, 800
    GRAY = "#6e757e"
    o: list[str] = []
    add = o.append

    def box(x, y, w, h, title, lines=(), core=False, optional=False, mono=False):
        stroke = t["lime"] if core else (t["cyan"] if optional else t["line"])
        dash = ' stroke-dasharray="6 5"' if optional else ""
        add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{t["surface"]}" stroke="{stroke}" '
            f'stroke-width="1.6"{dash}/>')
        add(f'<text x="{x + 14}" y="{y + 25}" font-family="{SANS}" font-size="15" font-weight="700" fill="{t["text"]}">{title}</text>')
        for i, ln in enumerate(lines):
            add(f'<text x="{x + 14}" y="{y + 46 + i * 18}" font-family="{MONO if mono else SANS}" font-size="12.5" '
                f'fill="{t["sub"]}">{ln}</text>')

    def arrow(d, kind="flow", both=False):
        color, dash, mk = {"flow": (t["lime"], "", "a"), "opt": (t["cyan"], ' stroke-dasharray="6 5"', "c"),
                           "disk": (GRAY, "", "g")}[kind]
        start = f' marker-start="url(#{mk})"' if both else ""
        add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#{mk})"{start}/>')

    def step(x, y, n):
        add(f'<circle cx="{x}" cy="{y}" r="11" fill="{t["lime"]}"/>')
        add(f'<text x="{x}" y="{y + 4.5}" text-anchor="middle" font-family="{SANS}" font-size="12.5" font-weight="800" '
            f'fill="{t["lime_ink"]}">{n}</text>')

    def label(x, y, s, color=None, anchor="start"):
        add(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="{MONO}" font-size="11.5" '
            f'fill="{color or t["sub"]}">{s}</text>')

    def lane(x, w, title, sub):
        add(f'<rect x="{x}" y="78" width="{w}" height="560" rx="14" fill="#ffffff" fill-opacity="0.015" '
            f'stroke="{t["line"]}" stroke-dasharray="3 6"/>')
        add(f'<text x="{x + 16}" y="102" font-family="{MONO}" font-size="12" font-weight="700" letter-spacing="1.5" '
            f'fill="{t["lime"]}">{title}</text>')
        add(f'<text x="{x + 16}" y="120" font-family="{SANS}" font-size="12" fill="{t["muted"]}">{sub}</text>')

    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">')
    add('<title id="t">higgsfield-scraper — container view of one run</title>')
    add('<desc id="d">Numbered data flow: CLI and run manager start a run; the scraper spider requests Higgsfield JSON '
        'APIs through auth and archive middlewares; parsers turn responses into entities; pipelines archive, validate, '
        'dedup and export them into a timestamped run folder.</desc>')
    add('<defs>' + "".join(
        f'<marker id="{i}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M0 0L10 5L0 10z" fill="{c}"/></marker>' for i, c in (("a", t["lime"]), ("c", t["cyan"]), ("g", GRAY))) + '</defs>')
    add(f'<rect width="{W}" height="{H}" rx="18" fill="{t["bg"]}"/>')
    add(f'<text x="32" y="44" font-family="{SANS}" font-size="22" font-weight="800" fill="{t["text"]}">higgsfield-scraper '
        f'<tspan fill="{t["lime"]}">·</tspan> container view of one run</text>')
    add(f'<text x="34" y="66" font-family="{SANS}" font-size="13" fill="{t["muted"]}">Data flows left → right. '
        f'Numbers give the order of events. Same machinery for all 10 scrapers; the export command then turns finished runs into dataset folders.</text>')

    # lanes (trust boundaries)
    lane(20, 270, "HIGGSFIELD", "external systems (read-only)")
    lane(306, 650, "SCRAPER PROCESS", "python -m higgsfield_scraper  ·  Scrapy + pydantic")
    lane(972, 288, "LOCAL DISK", "runs/&lt;timestamp&gt;_&lt;label&gt;/")

    # external
    box(36, 136, 238, 92, "fnf-api-gw · cms.higgsfield.ai", ["plans · costs · publications ·", "folders · community · CMS lists",
                                                                 "marketplaces · academy"], core=True)
    box(36, 244, 238, 74, "pricing.higgsfield.ai", ["pricing-config (marketing copy)"])
    box(36, 334, 238, 74, "higgsfield.ai", ["pages · sitemaps · examples", "JS bundle (model registry)"])
    box(36, 424, 238, 92, "Clerk auth", ["login once (emailed code)", "→ fresh 60 s tokens"], optional=True)
    box(36, 532, 238, 74, "Media CDN", ["images · videos (opt-in)"], optional=True)

    # process
    box(322, 136, 190, 92, "CLI · menu", ["scrape &lt;scraper&gt; [options]", "menu · export · diff · login"], mono=False)
    box(322, 244, 190, 74, "RunManager", ["run folder · logs · manifest"])
    add(f'<rect x="322" y="334" width="190" height="272" rx="12" fill="none" stroke="{t["line"]}" stroke-dasharray="4 4"/>')
    add(f'<text x="336" y="356" font-family="{MONO}" font-size="11.5" font-weight="700" letter-spacing="1" '
        f'fill="{t["muted"]}">DOWNLOADER MIDDLEWARE</text>')
    box(334, 368, 166, 100, "AuthMiddleware", ["adds Bearer token", "refresh + retry on 401", "skips if no login"])
    box(334, 482, 166, 110, "HttpArchive", ["request · response", "body · curl · HAR", "secrets masked"])

    box(556, 136, 196, 128, "Spider", ["one per scraper", "requests · pagination", "limits · stop on captcha", "(no evasion)"], core=True)
    box(556, 302, 196, 92, "Parsers (pure)", ["raw JSON / HTML → entities", "reused by normalize"], core=True)
    box(556, 430, 196, 92, "Cost estimator", ["generation → credits", "+ USD (opt-in)"], optional=True)

    pipes = [("RawArchive", ["untouched → raw/"]), ("Validation", ["pydantic v2 · drop invalid"]),
             ("Dedup", ["stable ids"]), ("Assemble + export", ["joins · JSON · CSV", "schema · summary"])]
    py = 136
    for i, (title, lines) in enumerate(pipes):
        h = 92 if i == 3 else 74
        box(776, py, 164, h, title, lines, core=(i == 3))
        if i < 3:
            arrow(f"M858 {py + h} V{py + h + 16}")
        py += h + 16

    # disk tree with writer tags
    add(f'<rect x="988" y="136" width="256" height="470" rx="12" fill="{t["surface"]}" stroke="{t["line"]}" stroke-width="1.6"/>')
    rows = [("manifest.json", "RunManager"), ("logs/", "RunManager"), ("raw/", "RawArchive"), ("http/", "HttpArchive"),
            ("media/", "Spider (opt-in)"), ("output/", "Assemble + export"), ("  dataset.json", ""), ("  json/  csv/", ""),
            ("  schema/", ""), ("  items/  summary.md", "")]
    for i, (name, who) in enumerate(rows):
        y = 168 + i * 34
        sub = name.startswith("  ")
        add(f'<text x="{1026 if sub else 1004}" y="{y}" font-family="{MONO}" font-size="13" '
            f'fill="{t["text"] if sub else t["cyan"]}">{name.strip()}</text>')
        if who:
            add(f'<text x="1230" y="{y}" text-anchor="end" font-family="{SANS}" font-size="11.5" fill="{t["muted"]}">← {who}</text>')
    add(f'<text x="1004" y="528" font-family="{SANS}" font-size="12" fill="{t["muted"]}">also: runs/LATEST · index.jsonl · exports/</text>')
    add(f'<text x="1004" y="550" font-family="{SANS}" font-size="12" fill="{t["muted"]}">exit 0 ok · 3 partial · 4 blocked · 1 fail</text>')
    add(f'<text x="1004" y="580" font-family="{SANS}" font-size="12" fill="{t["muted"]}">JSON indent 4 · CSVs complete</text>')

    # flows (numbered, labelled, edge-to-edge)
    arrow("M417 228 V242"); step(440, 236, 1); label(456, 240, "start run")
    arrow("M512 182 H554"); step(533, 166, 2); label(516, 205, "selection", anchor="start")
    arrow("M556 236 C 520 252, 532 340, 502 404"); step(538, 290, 3); label(528, 326, "GET", anchor="end")
    arrow("M332 420 C 300 420, 300 182, 276 182", both=True); step(300, 300, 4); label(300, 330, "HTTPS", anchor="middle")
    arrow("M334 520 C 312 520, 298 470, 276 470", kind="opt", both=True); label(300, 512, "token", color=t["cyan"], anchor="end")
    arrow("M276 570 C 300 570, 310 560, 332 560", kind="opt"); label(304, 590, "media", color=t["cyan"], anchor="end")
    arrow("M654 264 V300"); step(674, 283, 5); label(690, 287, "JSON")
    arrow("M752 348 C 766 348, 760 175, 774 175"); step(764, 254, 6)
    arrow("M654 430 V396", kind="opt", both=True); label(664, 418, "estimate", color=t["cyan"])
    arrow("M940 175 H986", kind="disk"); label(946, 168, "raw/", color=GRAY)
    arrow("M940 420 C 960 420, 962 338, 986 338", kind="disk"); step(963, 395, 7); label(946, 450, "output/", color=GRAY)
    arrow("M500 592 C 700 625, 900 625, 1010 608", kind="disk"); label(760, 630, "http/  (every exchange)", color=GRAY, anchor="middle")

    # legend
    add(f'<rect x="20" y="652" width="1240" height="130" rx="14" fill="{t["surface"]}" stroke="{t["line"]}"/>')
    add(f'<text x="38" y="678" font-family="{MONO}" font-size="12" font-weight="700" letter-spacing="1.5" fill="{t["lime"]}">LEGEND</text>')
    lx, ly = 38, 704
    items = [("flow", "main data flow"), ("opt", "optional: login · media · estimates"), ("disk", "writes to disk")]
    for i, (k, txt) in enumerate(items):
        x = lx + i * 300
        arrow(f"M{x} {ly} H{x + 46}", kind=k)
        add(f'<text x="{x + 58}" y="{ly + 4}" font-family="{SANS}" font-size="13" fill="{t["sub"]}">{txt}</text>')
    bx = [("core", "core component", t["lime"], ""), ("opt", "optional / opt-in component", t["cyan"], ' stroke-dasharray="6 5"'),
          ("std", "component", t["line"], ""), ("lane", "lane = trust boundary", t["line"], ' stroke-dasharray="3 6"')]
    for i, (_, txt, col, dash) in enumerate(bx):
        x = lx + i * 300
        add(f'<rect x="{x}" y="728" width="46" height="22" rx="6" fill="{t["bg"]}" stroke="{col}" stroke-width="1.6"{dash}/>')
        add(f'<text x="{x + 58}" y="744" font-family="{SANS}" font-size="13" fill="{t["sub"]}">{txt}</text>')
    step(lx + 1200 - 250, 704, 1)
    add(f'<text x="{lx + 1200 - 232}" y="708" font-family="{SANS}" font-size="13" fill="{t["sub"]}">order of events</text>')
    add(f'<text x="38" y="772" font-family="{SANS}" font-size="12" fill="{t["muted"]}">Double-headed arrows = request + response. '
        f'Only GET requests are sent; mutating endpoints (buy, vote, generate…) are never called.</text>')
    add("</svg>")
    return "\n".join(o) + "\n"


# Scraper overview cards: (name, tag, three short lines). Tags: default · public · opt-in · login.
CARDS = [
    ("pricing", "default", ["plans · offers · renewals", "credit cost of every model", "benefits · compare · copy"]),
    ("community", "public", ["gallery generations + prompts", "shots · posts · creators", "comments · cost estimate"]),
    ("catalog", "public", ["motions · avatars · voices", "styles · viral presets", "chain · restyle · outfits"]),
    ("projects", "public", ["films · contests · entries", "assets · briefs · comments", "trending · user works"]),
    ("blog", "public", ["blog · talent posts", "help centers · case studies", "changelog (full text)"]),
    ("site", "public", ["apps · academy (+ JSON API)", "MCP skills · original series", "landings · rooms · promos"]),
    ("showcase", "public", ["Canvas · Editing Room", "video explore · effects", "reels · main feed · API docs"]),
    ("studios", "opt-in", ["apps · games · skills", "AI employees · playable ads", "studio galleries + comments"]),
    ("models", "opt-in", ["JS model registry per build", "params · enums · limits", "gating · plans · costs"]),
    ("account", "login", ["your plan · balances", "your jobs + real credits", "estimate vs actual"]),
]
CARD_FONT = 12.5


def text_width(s: str, size: float, mono: bool = False) -> float:
    """Rough advance width: mono 0.62 em, sans (Inter/Segoe) ≈ 0.56 em average for this text."""
    return len(s) * size * (0.62 if mono else 0.56)


def scrapers_overview() -> str:
    """The 10 scrapers as cards in two rows (dark theme), with what each collects and the tools that follow."""
    t = THEMES["dark"]
    W, PAD, GAP, CW, CH = 1280, 32, 16, 230, 124
    tag_col = {"default": t["lime"], "public": t["sub"], "opt-in": t["cyan"], "login": t["pink"]}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="490" viewBox="0 0 {W} 490" role="img" aria-labelledby="st sd">',
         '<title id="st">higgsfield-scraper — the 10 scrapers</title>',
         '<desc id="sd">Ten scrapers and what each collects: ' + "; ".join(f"{n} ({g}): {', '.join(ls)}" for n, g, ls in CARDS)
         + '. Then export, merge_generations, diff and the interactive menu.</desc>',
         f'<rect width="{W}" height="490" rx="18" fill="{t["bg"]}"/>',
         f'<text x="{PAD}" y="44" font-family="{SANS}" font-size="22" font-weight="800" fill="{t["text"]}">higgsfield-scraper '
         f'<tspan fill="{t["lime"]}">·</tspan> 10 scrapers</text>',
         f'<text x="{PAD + 2}" y="66" font-family="{SANS}" font-size="13" fill="{t["muted"]}">'
         f'<tspan fill="{t["lime"]}">default</tspan> = what <tspan font-family="{MONO}">scrape</tspan> runs · '
         f'<tspan fill="{t["sub"]}">public</tspan> = no login · <tspan fill="{t["cyan"]}">opt-in</tspan> = public, run by name · '
         f'<tspan fill="{t["pink"]}">login</tspan> = your own account only. Every scraper has more opt-in options (CLI.md).</text>']
    assert PAD * 2 + CW * 5 + GAP * 4 <= W
    for i, (name, tag, lines) in enumerate(CARDS):
        x = PAD + (i % 5) * (CW + GAP)
        y = 88 + (i // 5) * (CH + GAP)
        col = tag_col[tag]
        o.append(f'<rect x="{x}" y="{y}" width="{CW}" height="{CH}" rx="12" fill="{t["surface"]}" '
                 f'stroke="{t["lime"] if tag == "default" else t["line"]}" stroke-width="1.6"/>')
        o.append(f'<text x="{x + 14}" y="{y + 28}" font-family="{MONO}" font-size="16" font-weight="700" fill="{t["text"]}">{name}</text>')
        tw = text_width(tag, 11, mono=True) + 16
        assert 14 + text_width(name, 16, mono=True) + 8 + tw <= CW - 10, f"{name}: name + tag overflow"
        o.append(f'<rect x="{x + CW - 12 - tw}" y="{y + 12}" width="{tw}" height="22" rx="11" fill="none" stroke="{col}" stroke-width="1.2"/>')
        o.append(f'<text x="{x + CW - 12 - tw / 2}" y="{y + 27}" text-anchor="middle" font-family="{MONO}" font-size="11" '
                 f'fill="{col}">{tag}</text>')
        for j, ln in enumerate(lines):
            assert 14 + text_width(ln, CARD_FONT) <= CW - 12, f"{name}: line {ln!r} overflows the card"
            o.append(f'<text x="{x + 14}" y="{y + 60 + j * 20}" font-family="{SANS}" font-size="{CARD_FONT}" fill="{t["sub"]}">{ln}</text>')
    y = 88 + 2 * (CH + GAP) + 4
    o.append(f'<rect x="{PAD}" y="{y}" width="{W - 2 * PAD}" height="94" rx="12" fill="{t["surface"]}" stroke="{t["cyan"]}" '
             f'stroke-width="1.4" stroke-dasharray="6 5"/>')
    o.append(f'<text x="{PAD + 16}" y="{y + 28}" font-family="{MONO}" font-size="12" font-weight="700" letter-spacing="1.5" '
             f'fill="{t["lime"]}">THEN, ON THE RUN FOLDERS</text>')
    tools = [("export", "tree · Hugging Face · WebDataset · JSONL"), ("merge_generations.py", "count + dedupe across runs"),
             ("diff · crosscheck", "pricing changes · vs pricing.md"), ("menu", "interactive mode")]
    tx = PAD + 16
    for name, sub in tools:
        o.append(f'<text x="{tx}" y="{y + 56}" font-family="{MONO}" font-size="14" font-weight="600" fill="{t["text"]}">{name}</text>')
        o.append(f'<text x="{tx}" y="{y + 76}" font-family="{SANS}" font-size="12.5" fill="{t["sub"]}">{sub}</text>')
        tx += 300
        assert tx - 300 + max(text_width(name, 14, True), text_width(sub, 12.5)) <= W - PAD - 8, f"{name} overflows"
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "banner-dark.svg").write_text(banner(THEMES["dark"]), encoding="utf-8")
    (OUT / "banner-light.svg").write_text(banner(THEMES["light"]), encoding="utf-8")
    (OUT / "architecture.svg").write_text(architecture(), encoding="utf-8")
    (OUT / "scrapers.svg").write_text(scrapers_overview(), encoding="utf-8")
    old = OUT / "banner.svg"
    if old.exists():
        old.unlink()
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
