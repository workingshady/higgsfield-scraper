"""Generate docs/higgsfield.postman_collection.json — every endpoint the scrapers use, grouped by scraper.

    python scripts/make_postman.py

Variables: api_base, pricing_base, site_base, clerk_base, locale, plan_set_key, billing_period, size, cursor,
token (Clerk session JWT), client_cookie (__client), sign_in_id, session_id, email, password, code.
Login-only requests use Bearer {{token}}. The "Login (Clerk)" folder reproduces `python -m higgsfield_scraper login`.
GET requests only, except the Clerk login/token flow.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from higgsfield_scraper.constants import PLAN_SET_KEYS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "docs" / "higgsfield.postman_collection.json"
H = [{"key": "Accept", "value": "application/json"}, {"key": "Origin", "value": "https://higgsfield.ai"},
     {"key": "Referer", "value": "https://higgsfield.ai/"}]
OK = ["pm.test('HTTP 200', () => pm.response.to.have.status(200));"]
JSON_OK = OK + ["pm.test('JSON body', () => pm.response.to.be.json);"]


def req(name, path, query=(), desc="", auth=False, base="{{api_base}}", tests=JSON_OK, method="GET", form=None):
    q = [{"key": k, "value": v} for k, v in query]
    raw = f"{base}{path}" + ("?" + "&".join(f"{k}={v}" for k, v in query) if query else "")
    r = {"method": method, "header": list(H), "url": {"raw": raw, "host": [base], "path": [p for p in path.strip("/").split("/") if p],
                                                         "query": q}, "description": desc}
    r["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]} if auth else {"type": "noauth"}
    if form is not None:
        r["header"] = r["header"] + [{"key": "Content-Type", "value": "application/x-www-form-urlencoded"},
                                     {"key": "Cookie", "value": "__client={{client_cookie}}"}]
        r["body"] = {"mode": "urlencoded", "urlencoded": [{"key": k, "value": v} for k, v in form]}
    return {"name": name + ("  🔒" if auth else ""), "request": r,
            "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": list(tests)}}]}


def folder(name, desc, items):
    return {"name": name, "description": desc, "item": items}


S = [("size", "{{size}}")]
pricing = folder("pricing", "Plans, offers, model credit costs, benefits, comparison, marketing copy (docs/ENDPOINTS.md).", [
    req("Plans (before/after offer)", "/subscriptions/v2/plans", [("with_localization", "true"), ("plan_set_key", "{{plan_set_key}}")],
        "Cents. original_*=before offer, final_*=after offer, renew_*=renewal. country_code from IP."),
    req("Plan comparison matrix", "/subscriptions/v2/compare",
        [("plan_set_key", "{{plan_set_key}}"), ("billing_period", "{{billing_period}}"), ("with_localization", "true")]),
    req("Plan benefits", "/subscriptions/v2/plan-benefits", [("locale", "{{locale}}")], "Card sections; job_set_types join to costs."),
    req("Model credit costs", "/job-sets/costs", (), "86+ job_set_types; `version` = content hash."),
    req("Marketing config (all versions)", "/v2/pricing-config", [("locale", "{{locale}}")], base="{{pricing_base}}"),
    req("Marketing config (one version)", "/v2/pricing-config", [("planVersion", "v51.0.0"), ("locale", "{{locale}}")], base="{{pricing_base}}"),
    req("Plan-set enum (expect 422)", "/subscriptions/v2/plans", [("plan_set_key", "__list__")],
        "The 422 message lists every valid plan_set_key.", tests=["pm.test('422', () => pm.response.to.have.status(422));"]),
    req("Credit top-up packages", "/subscriptions/v2/packages", auth=True),
    req("Unlimited bundles catalog", "/subscriptions/bundle/unlim-catalog", auth=True),
    req("Credit price", "/workspaces/credit-price", auth=True),
    req("Adjustable credits", "/subscriptions/v2/adjustable-credits", auth=True),
])
community = folder("community", "Public generations (prompt, settings, results, engagement). docs/scrapers/community.md.", [
    req("Trending generations", "/publications/community/trending", [("size", "50"), ("cursor", "{{cursor}}"), ("type", "image")],
        "size ≤ 50; cursor = float score from previous page; type image|video|speak|upscale; model= repeatable job_set_type."),
    req("Approved generations", "/publications/community/approved", [("size", "100"), ("cursor", "{{cursor}}")],
        "Curated feed (~6.7k); videos live here (mostly viral_hub_video). cursor = unix timestamp."),
    req("Top generations", "/publications/community/trending/top", [("size", "100")], "Single page, no cursor."),
    req("Model-x showcase", "/publications/community/model-x", [("size", "50")]),
    req("Generation detail", "/publications/{{publication_id}}"),
    req("Community posts feed (fnf-community)", "/publications/feed", [("limit", "20"), ("offset", "0")],
        "Separate Community posts service; used by --with-comments to find posts with comment_count > 0.",
        base="{{community_base}}"),
    req("Post comments (fnf-community)", "/publications/{{community_post_id}}/comments",
        [("limit", "50"), ("offset", "0")], "Public. Gallery publication ids are not posts here (always []).",
        base="{{community_base}}"),
    req("Comment replies (fnf-community)", "/publications/{{community_post_id}}/comments",
        [("limit", "50"), ("parent_id", "{{comment_id}}")], base="{{community_base}}"),
    req("Related publications (fnf-community)", "/publications/{{community_post_id}}/related", [("limit", "10")],
        base="{{community_base}}"),
    req("Viral presets (price matrices)", "/viral-hub/presets/all", [("lang", "{{locale}}")],
        "Used by --estimate-cost to price viral_hub_video generations (credit_units / 100)."),
])
public_catalog = [
    ("Motions (all families)", "/motions", [("size", "1000")], "419 presets; cursor = negative int priority."),
    ("Motion detail", "/motions/{{motion_id}}", (), "Real preview media + description."),
    ("Motion samples", "/motion-samples", [("motion_id", "{{motion_id}}"), ("size", "20")], "motion_id + size required."),
    ("Avatars", "/avatars", [("size", "200")], "size > 200 -> HTTP 500."),
    ("Avatar presets", "/avatar-presets", [("size", "200")], ""),
    ("Voices", "/voices", [("size", "500")], ""),
    ("Reference voices", "/reference-elements/voices", [("size", "500")], "has_more + user_cursor/preset_cursor."),
    ("Sounds", "/sounds", [("size", "500")], ""),
    ("Styles", "/styles", [("size", "500")], ""),
    ("Soul samples", "/soul-samples", [("size", "2000")], "~1,263 Soul example generations."),
    ("Viral types", "/viral-hub/types", [("lang", "{{locale}}")], ""),
    ("Viral presets", "/viral-hub/presets/all", [("lang", "{{locale}}")], "87 presets with price matrix + inputs."),
]
# opt-in catalogs (verified 2026-11-26): public on the CMS host / fnf-cms-api; fnf/<path> is 404 even with a login
cms_catalog = ["/soul-styles", "/soul-cinematic-styles", "/soul-keyframe-styles", "/mixed-media-presets", "/veo3-styles",
               "/kling-motions", "/kling2-6-motions", "/seedance-motions", "/wan2-2-motions", "/wan2-5-motions",
               "/minimax-motions", "/youtube-faceless-presets"]
catalog = folder("catalog", "Preset & asset catalogs. docs/scrapers/catalog.md.",
                 [req(n, p, q, d) for n, p, q, d in public_catalog]
                 + [req(p.strip("/").replace("-", " ").title() + " (CMS)", p, [("size", "100"), ("lang", "{{locale}}")],
                        "Public on cms.higgsfield.ai; cursor = next page number.", base="{{cms_base}}")
                    for p in cms_catalog]
                 + [req("Marketing Studio v2 catalog (CMS)", "/marketing-studio-v2/catalog",
                        [("lang", "{{locale}}"), ("show_hidden", "false")], "Categories (id = slug) with formats.",
                        base="{{cms_base}}"),
                    req("Marketing Studio v2 presets (CMS)", "/marketing-studio-v2/categories/{{marketing_category}}/presets",
                        [("size", "100"), ("lang", "{{locale}}"), ("show_hidden", "false")], "Per category slug (e.g. ugc).",
                        base="{{cms_base}}"),
                    req("Katana categories", "/katana-categories", [("limit", "100"), ("lang", "{{locale}}")],
                        "fnf-cms-api; limit 1..100, next_cursor.", base="{{cms_api_base}}"),
                    req("Katana presets", "/katana-presets", [("limit", "100"), ("lang", "{{locale}}")],
                        "fnf-cms-api; next_cursor (opaque).", base="{{cms_api_base}}"),
                    req("Color presets", "/color-presets", [("size", "100")], "Needs a session.", auth=True),
                    req("Camera settings", "/camera-settings", (), "Needs a session (account data).", auth=True),
                    # opt-in extras (catalog --kinds chain_preset,notice,restyle_preset; public, verified 2026-11-26)
                    req("Job-set chain presets", "/job-set-chain-presets", [("lang", "{{locale}}")],
                        "fnf-cms-api; one JSON array (48), no paging. cost_credits / discount_credits are credits "
                        "(no /100). catalog --kinds chain_preset.", base="{{cms_api_base}}"),
                    req("Job-set chain presets (+hidden)", "/job-set-chain-presets",
                        [("show_hidden", "true"), ("lang", "{{locale}}")],
                        "58 = 48 visible + 10 hidden; no per-item hidden flag. catalog --include-hidden.",
                        base="{{cms_api_base}}"),
                    req("Notices (CMS)", "/notices", [("lang", "{{locale}}")],
                        "{header_notices[], job_set_notices[]}: per-model badges/popups (retirements, incidents). "
                        "catalog --kinds notice.", base="{{cms_base}}"),
                    req("Restyle presets", "/restyle-presets", [("size", "100"), ("lang", "{{locale}}")],
                        "fnf-cms-api; {total, cursor (next page number), items}. catalog --kinds restyle_preset.",
                        base="{{cms_api_base}}")])
projects = folder("projects", "Project showcases (films/series), contests, submissions. docs/scrapers/projects.md.", [
    req("Project publications", "/project-publications", [("limit", "50"), ("cursor", "{{cursor}}")], "cursor = score; ends when next_cursor null."),
    req("Recommended publications", "/project-publications/recommended", [("scope", "community"), ("limit", "50")],
        "scope: community | ai_film_festival | talent_contest | ad_contest | discord."),
    req("Publication categories", "/project-publications/categories"),
    req("Publication detail", "/project-publications/{{publication_id}}", (), "Adds models used + credits spent."),
    req("Contests (global)", "/contests"),
    req("Contests (weekly)", "/contests", [("contest_type", "weekly")]),
    req("Contest detail", "/contests/by-id/{{contest_id}}", (), "settings, rewards, prizes, rules, FAQ, timeline, winners."),
    req("Contest submissions", "/contests/{{contest_id}}/submissions", [("limit", "100"), ("ordering", "newest")],
        "ordering: newest | most-liked | most-viewed | trending."),
    req("Contest entries", "/contest-participations/publications", [("tab", "ai_film_festival"), ("limit", "100")]),
    req("Series", "/series", auth=True, desc="Legacy fnf path used by the default run: 401 without a session, 404 with "
        "one. Use the fnf-series requests below."),
    req("Series detail", "/series/{{slug}}", auth=True, desc="Legacy fnf path (404). Use fnf-series below."),
    req("Series (fnf-series, public)", "/series", [("limit", "100")],
        "Public, no login: {items, total} (35). projects --what series --public-series.", base="{{series_base}}"),
    req("Series detail (fnf-series, public)", "/series/{{slug}}", (),
        "Public. projects --public-series --with-details.", base="{{series_base}}"),
    # nested project data (projects --with-project-*, --contest, --users); all public GETs, no realm header
    req("Contest by slug", "/contests/{{contest_slug}}", (), "Same body as /contests/by-id/{id}. projects --contest <slug>."),
    req("Publication by handle/slug", "/project-publications/{{handle}}/{{slug}}", (),
        "The page /@handle/projects/slug; same body as the detail by id."),
    req("Project root folder", "/folders/{{folder_id}}", (),
        "folder_id = detail snapshot_folder_id. name, count ('All assets'), subfolders_count. --with-project-assets."),
    req("Project sub-folders", "/folders/{{folder_id}}/children", (), "Cast, Locations, Scenes … with counts; recurse "
        "while subfolders_count > 0."),
    req("Project assets", "/folders/{{folder_id}}/items/v2", [("size", "100"), ("include_subfolders", "true"),
                                                             ("cursor", "{{cursor}}")],
        "Jobs (prompt, params, job_set_type, results raw/min) and uploads. size <= 100; cursor = epoch float. "
        "Watermarks sub-folder: list it on its own."),
    req("Project brief snapshot (binary Yjs)", "/brief/{{folder_id}}/snapshot", (),
        "Yjs v1 update of the Lexical brief; header X-Brief-Updated-At. --with-project-brief renders Markdown.",
        base="{{brief_base}}", tests=OK),
    req("Project comments (fnf-community)", "/entities/project_publication/{{publication_id}}/comments",
        [("limit", "100"), ("cursor", "{{cursor}}")], "{items, total, next_cursor}. --with-project-comments.",
        base="{{community_base}}"),
    req("Project comment replies (fnf-community)", "/entities/project_publication/{{publication_id}}/comments",
        [("limit", "100"), ("parent_id", "{{comment_id}}"), ("order", "asc")], base="{{community_base}}"),
    req("Related projects", "/project-publications/recommended",
        [("scope", "talent_contest"), ("current_publication_id", "{{publication_id}}")],
        "The page's related list: scope by contest_key (community | talent_contest | ai_film_festival). "
        "--with-project-related."),
    req("User projects (profile tab)", "/user/{{handle}}/v2/publications",
        [("publication_type", "project"), ("limit", "50"), ("cursor", "{{cursor}}")],
        "{publications, has_more, cursor, total}. projects --users <handle>."),
])
blog = folder("blog", "Written content. Company posts/help/changelog are SSR pages (data embedded as $_TSR state); "
              "talent posts via API (Yjs bodies). docs/scrapers/blog.md.", [
    req("Blog index (SSR HTML)", "/blog", base="{{site_base}}", tests=OK),
    req("Blog post (SSR HTML)", "/blog/{{slug}}", base="{{site_base}}", tests=OK),
    req("Blog sitemap", "/blog/sitemap.xml", base="{{site_base}}", tests=OK),
    req("Help center index (SSR HTML)", "/creator-hub/help-center", base="{{site_base}}", tests=OK),
    req("Changelog (SSR HTML)", "/creator-hub/changelog", base="{{site_base}}", tests=OK),
    req("Case studies (SSR HTML)", "/creator-hub/case-studies", base="{{site_base}}", tests=OK),
    req("Enterprise help center (SSR HTML)", "/enterprise-help-center", base="{{site_base}}", tests=OK),
    req("Talent blog posts", "/community/discovery/talents/blog-posts", [("size", "50"), ("cursor", "{{cursor}}")]),
    req("Community posts feed", "/blog/posts/recommended", [("size", "50"), ("cursor", "{{cursor}}")]),
    req("Public post by uuid", "/blog/public/posts/{{post_id}}", (), "UUID only (slug -> 422)."),
    req("All blog posts", "/blog/posts", auth=True),
])
site = folder("site", "Public site pages not covered elsewhere: apps, academy, MCP skills, original series, mixed-media presets, "
              "landing pages (SSR HTML; data embedded as $_TSR loader state, landings = <main> + JSON-LD) and three small "
              "promo APIs. docs/scrapers/site.md.", [
    req("Apps index (SSR HTML)", "/apps", base="{{site_base}}", tests=OK),
    req("App page (SSR HTML)", "/apps/{{slug}}", base="{{site_base}}", tests=OK, desc="appPreset with templates and credit cost."),
    req("Apps sitemap", "/apps/sitemap.xml", base="{{site_base}}", tests=OK),
    req("Academy courses (SSR HTML)", "/academy/courses", base="{{site_base}}", tests=OK),
    req("Course page (SSR HTML)", "/academy/courses/{{course}}", base="{{site_base}}", tests=OK),
    req("Lesson page (SSR HTML)", "/academy/courses/{{course}}/{{lesson}}", base="{{site_base}}", tests=OK,
        desc="lesson + mdxTree (HAST) body."),
    req("Academy sitemap", "/academy/sitemap.xml", base="{{site_base}}", tests=OK),
    req("MCP skills index (SSR HTML)", "/mcp", base="{{site_base}}", tests=OK),
    req("MCP skill (SSR HTML)", "/mcp/{{slug}}", base="{{site_base}}", tests=OK),
    req("MCP bundle (SSR HTML)", "/mcp/bundles/{{slug}}", base="{{site_base}}", tests=OK),
    req("Original series index (SSR HTML)", "/original-series", base="{{site_base}}", tests=OK),
    req("Original series episode (SSR HTML)", "/original-series/{{series}}/{{episode}}", base="{{site_base}}", tests=OK),
    req("Original series sitemap", "/original-series/sitemap.xml", base="{{site_base}}", tests=OK),
    req("Mixed-media preset (SSR HTML)", "/mixed-media-presets/preset/{{preset_id}}", base="{{site_base}}", tests=OK),
    req("Mixed-media sitemap", "/mixed-media-presets/sitemap.xml", base="{{site_base}}", tests=OK),
    req("Marketing sitemap (landings, plugins, MCP, rooms)", "/sitemap-marketing.xml", base="{{site_base}}", tests=OK),
    req("Landing page (SSR HTML)", "/ai-image", base="{{site_base}}", tests=OK, desc="<main> + JSON-LD (FAQPage, HowTo, SoftwareApplication)."),
    req("Promo schedule", "/datetime-settings", (), "Sale / free-gens / release windows."),
    req("Business unlimited offers", "/business-unlim/state"),
    req("Game gift networks", "/game-gift/networks"),
])
clerk = folder("Login (Clerk)", "Reproduces `python -m higgsfield_scraper login` (password -> emailed code -> session) and "
               "token minting. Base {{clerk_base}} = https://higgsfield.ai/_clerk. Every call needs the query "
               "params __clerk_api_version=2026-11-18&_clerk_js_version=6.46.3 and a Cookie: __client=... (set "
               "{{client_cookie}} from the Set-Cookie of step 1). Never share these values.", [
    req("1. Client (anonymous __client cookie)", "/v1/client", [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")],
        base="{{clerk_base}}"),
    req("Environment (sign-in methods)", "/v1/environment", [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")],
        base="{{clerk_base}}"),
    req("2. Sign in with password", "/v1/client/sign_ins", [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")],
        base="{{clerk_base}}", method="POST", form=[("identifier", "{{email}}"), ("strategy", "password"), ("password", "{{password}}")],
        desc="-> status needs_second_factor (new device): save response.id as {{sign_in_id}}."),
    req("3. Send emailed code", "/v1/client/sign_ins/{{sign_in_id}}/prepare_second_factor",
        [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")], base="{{clerk_base}}", method="POST",
        form=[("strategy", "email_code")]),
    req("4. Submit code", "/v1/client/sign_ins/{{sign_in_id}}/attempt_second_factor",
        [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")], base="{{clerk_base}}", method="POST",
        form=[("strategy", "email_code"), ("code", "{{code}}")], desc="-> status complete; created_session_id = {{session_id}}."),
    req("5. Mint session token (~60 s)", "/v1/client/sessions/{{session_id}}/tokens",
        [("__clerk_api_version", "2026-11-18"), ("_clerk_js_version", "6.46.3")], base="{{clerk_base}}", method="POST", form=[],
        desc="-> {jwt}. Put it in {{token}} for the 🔒 requests. Repeat whenever it expires."),
])

col = {
    "info": {"name": "Higgsfield (unofficial) — all scraper endpoints",
             "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
             "description": "Reverse-engineered, read-only endpoints used by higgsfield-scraper "
                            "(https://github.com/workingshady/higgsfield-scraper). 🔒 = needs {{token}} (see 'Login (Clerk)'). "
                            "plan_set_key=ps_a3 = US prices. Unofficial; not affiliated with Higgsfield."},
    "variable": [{"key": k, "value": v} for k, v in [
        ("api_base", "https://fnf-api-gw.higgsfield.ai/fnf"), ("pricing_base", "https://pricing.higgsfield.ai"),
        ("cms_base", "https://cms.higgsfield.ai"), ("cms_api_base", "https://fnf-api-gw.higgsfield.ai/fnf-cms-api"),
        ("series_base", "https://fnf-api-gw.higgsfield.ai/fnf-series"),
        ("community_base", "https://fnf-api-gw.higgsfield.ai/fnf-community"), ("community_post_id", ""),
        ("comment_id", ""), ("marketing_category", "ugc"),
        ("site_base", "https://higgsfield.ai"), ("clerk_base", "https://higgsfield.ai/_clerk"), ("locale", "en"),
        ("plan_set_key", "ps_a3"), ("billing_period", "annual"), ("size", "50"), ("cursor", ""),
        ("publication_id", ""), ("motion_id", ""), ("contest_id", ""), ("slug", ""), ("post_id", ""), ("course", ""), ("lesson", ""), ("series", ""), ("episode", ""),
        ("preset_id", ""),
        ("brief_base", "https://dam-editor-worker.higgsfield.ai"), ("folder_id", ""), ("handle", ""),
        ("contest_slug", "talent-contest"),
        ("token", ""), ("client_cookie", ""), ("sign_in_id", ""), ("session_id", ""), ("email", ""), ("password", ""), ("code", "")]]
    + [{"key": "plan_set_keys_reference", "value": ", ".join(PLAN_SET_KEYS)}],
    "item": [pricing, community, catalog, projects, blog, site, clerk],
}
OUT.write_text(json.dumps(col, ensure_ascii=False, indent=4), encoding="utf-8")
print(f"wrote {OUT} — {sum(len(f['item']) for f in col['item'])} requests in {len(col['item'])} folders")
