"""Community-feed endpoints, page-size maxima and enums (reverse-engineered 2026-11-25, see docs/scrapers/community.md).

Base: https://fnf-api-gw.higgsfield.ai/fnf  (public, `Accept: application/json`).
"""
from __future__ import annotations

# feed name -> path
FEED_PATHS: dict[str, str] = {
    "trending": "/publications/community/trending",
    "approved": "/publications/community/approved",
    "top": "/publications/community/trending/top",
    "model-x": "/publications/community/model-x",
}
FEEDS = tuple(FEED_PATHS)

# feed name -> endpoint label (raw/ file prefix, stats key)
FEED_ENDPOINTS: dict[str, str] = {
    "trending": "community_trending",
    "approved": "community_approved",
    "top": "community_top",
    "model-x": "community_model_x",
}
ENDPOINT_FEEDS = {v: k for k, v in FEED_ENDPOINTS.items()}

DETAIL_ENDPOINT = "community_detail"            # GET /publications/{publication_id}
DETAIL_PATH = "/publications/{publication_id}"
# Comments live in the separate *Community posts* service (JS: Axe() = fnf-api-gw/fnf-community; verified
# 2026-11-26). They are public (200 with or without a session). Gallery publications (the feeds above) are NOT
# fnf-community publications: /fnf-community/publications/{gallery id} -> 404 and .../comments -> always
# {"comments": [], "has_more": false}; the old guess fnf/publications/{id}/comments -> 404 even when logged in.
# So --with-comments reads the Community posts feed and fetches the comments (+ replies) of posts that have any.
COMMUNITY_BASE = "https://fnf-api-gw.higgsfield.ai/fnf-community"
POSTS_ENDPOINT = "community_posts"              # GET {COMMUNITY_BASE}/publications/feed?limit=&offset=
POSTS_PATH = "/publications/feed"
POSTS_MAX_LIMIT = 50
COMMENTS_ENDPOINT = "community_comments"        # GET {COMMUNITY_BASE}/publications/{id}/comments?limit=&offset=&parent_id=
COMMENTS_PATH = "/publications/{publication_id}/comments"
COMMENTS_PAGE_SIZE = 50
JOB_COSTS_ENDPOINT = "community_job_costs"      # GET /job-sets/costs   (only with --estimate-cost)
JOB_COSTS_PATH = "/job-sets/costs"
PLANS_ENDPOINT = "community_plans"              # GET /subscriptions/v2/plans?plan_set_key=..&with_localization=true
PLANS_PATH = "/subscriptions/v2/plans"
COMPARE_ENDPOINT = "community_compare"          # GET /subscriptions/v2/compare (fallback prices; --estimate-cost)
COMPARE_PATH = "/subscriptions/v2/compare"
BENEFITS_ENDPOINT = "community_benefits"        # GET /subscriptions/v2/plan-benefits (label -> job_set_type)
BENEFITS_PATH = "/subscriptions/v2/plan-benefits"
VIRAL_ENDPOINT = "community_viral_presets"       # GET /viral-hub/presets/all (viral prices)
VIRAL_PATH = "/viral-hub/presets/all"

# feed -> (default page size, maximum we send).
#   trending / model-x: the API rejects size > 50 (HTTP 422 "less than or equal to 50")
#   top: the API rejects size > 100; it is a single page (no has_more, cursor ignored)
#   approved: the API accepted size=5000 in tests (no server maximum) — we cap at 200 to stay polite
PAGE_SIZE: dict[str, tuple[int, int]] = {
    "trending": (50, 50),
    "approved": (50, 200),
    "top": (100, 100),
    "model-x": (50, 50),
}

# query params each feed understands (others are not sent)
FEED_PARAMS: dict[str, frozenset[str]] = {
    "trending": frozenset({"type", "model", "preset_id", "resolution"}),
    "approved": frozenset({"type", "model", "preset_id", "resolution"}),
    "top": frozenset({"type"}),
    "model-x": frozenset(),
}

# `type` enum accepted by the API (422 otherwise). "all" = omit the parameter.
TYPES = ("all", "image", "video", "speak", "upscale")
# types the scraper can also enforce client-side (the approved feed ignores `type`)
CLIENT_FILTER_TYPES = ("image", "video")

ESTIMATE_MODES = ("off", "images", "videos", "all")

# ---------------------------------------------------------------- opt-in Community pages (added 2026-11-26)
# Values of --feeds that are NOT part of 'all' (which stays the four gallery feeds above). See
# docs/COMMUNITY_COVERAGE.md for the JS evidence (route chunks + query functions) and live checks.
#   shots    /community/generations ("Shots" tab): fnf-community GET /generations/feed?limit<=50&cursor&type&models
#            -> {items[], next_cursor, snapshot_id, snapshot_at, available_models[]}   (limit > 50 -> HTTP 400)
#   posts    Community posts: fnf-community GET /publications/feed?limit&offset -> {publications[], has_more}
#            (~24.3k posts on 2026-11-26, offset pagination, limit 100 accepted; we cap at 50)
#   feed     /community/feed ("Feed" tab): fnf-community GET /feed?limit<=50&cursor -> {items[{type: generation |
#            project_publication | blog_post | post, ...}], next_cursor, snapshot_id}
#   creators /community/creators: fnf GET /community/discovery/v2/creators?all=true&sort=&limit&cursor
#            -> {users[], total (646), next_cursor, next_offset, limit}
#   talents  Talents hub list: fnf GET /community/discovery/talents?sort=rating|trending|recent&limit&offset&size
#            -> {users[], total (80), limit, next_offset}
EXTRA_FEEDS = ("shots", "posts", "feed", "creators", "talents")
SHOTS_ENDPOINT = "community_shots"
SHOTS_PATH = "/generations/feed"
FEED_ENDPOINT = "community_feed"
FEED_PATH = "/feed"
POSTS_LIST_ENDPOINT = "community_posts_list"      # same URL as POSTS_ENDPOINT, but paginated and stored as items
CREATORS_ENDPOINT = "community_creators"
CREATORS_PATH = "/community/discovery/v2/creators"
TALENTS_ENDPOINT = "community_talents"
TALENTS_PATH = "/community/discovery/talents"
ENTITY_COMMENTS_ENDPOINT = "community_entity_comments"
# fnf-community GET /entities/{generation_publication|project_publication|blog_post}/{id}/comments?limit&cursor&parent_id
# -> {items[comment], next_cursor, total}. The JS (community-…: `na=({kind,id})=>N(/entities/${ta[kind]}/${id}/comments)`,
# page size ea=20) uses it for Feed/Shots items; gallery generations' comments live here (publication id).
ENTITY_COMMENTS_PATH = "/entities/{entity_type}/{entity_id}/comments"
ENTITY_COMMENTS_PAGE_SIZE = 20
EXTRA_PAGE_SIZE: dict[str, tuple[int, int]] = {      # feed -> (default, maximum we send)
    "shots": (50, 50), "posts": (50, 50), "feed": (50, 50), "creators": (50, 50), "talents": (50, 50)}
EXTRA_ENDPOINTS = {"shots": SHOTS_ENDPOINT, "posts": POSTS_LIST_ENDPOINT, "feed": FEED_ENDPOINT,
                   "creators": CREATORS_ENDPOINT, "talents": TALENTS_ENDPOINT}
# feed -> kind it produces (per-feed --max-items cap)
EXTRA_KINDS = {"shots": "community_shot", "posts": "community_post", "feed": "community_feed_item",
               "creators": "community_creator_stats", "talents": "community_creator_stats"}
FEED_ITEM_ENTITY = {"generation": "generation_publication", "project_publication": "project_publication",
                    "blog_post": "blog_post"}

USER_SEARCH_PATH = "/users/search"          # fnf-community; not used (would only return search results)
RELATED_PATH = "/publications/{publication_id}/related"  # fnf-community; not used

# `model` (job_set_type) values the trending/approved filter accepts — from the API 422 enum on 2026-11-25 (359 values).
# Unknown values make the API answer HTTP 422; the CLI only warns, since new models appear often.
KNOWN_MODELS: frozenset[str] = frozenset({
    'custom-image', 'custom-video', 'katana_preset_result', 'text2image', 'text2image_gpt', 'text2image_soul',
    'soul_cinematic', 'soul_cinema_1_5', 'soul_cinema_1_5_serega', 'meme_generator', 'text2image_soul_v2',
    'text2speech', 'flux_kontext', 'image2video', 'image2video_v2', 'wan2_2', 'wan2_2_video', 'wan2_2_image',
    'image2video_extend_v2', 'wan2_2_animate', 'wan2_2_animate_v2', 'wan2_2_animate_v3', 'wan2_2_animate_revoice',
    'image2video_mix', 'image2video_extend', 'canvas', 'canvas_soul', 'minimax_hailuo', 'minimax_hailuo_draw',
    'minimax_h3', 'minimax_h3_image', 'minimax_h3_max', 'minimax_h3_highspeed', 'minimax_h3_lite',
    'marketing_studio_v2_video', 'marketing_studio_v2_reference2video', 'marketing_studio_2_image',
    'ai_influencer_sheet', 'flux_3_image', 'flux_3_video', 'flux_3_video_edit', 'flux_video_upscale', 'seedance',
    'seedance_draw', 'veo3', 'veo3_1', 'veo3_1_lite', 'veo3_speak', 'veo3_1_speak', 'veo3_draw', 'topaz_image',
    'topaz_image_generative', 'topaz_video', 'topaz_hyperion_2_5', 'kling', 'kling_speak', 'nano_banana',
    'nano_banana_animal', 'nano_banana_clothing_cleaner', 'nano_banana_2', 'nano_banana_pro', 'nano_banana_2_lite',
    'nano_banana_flash', 'nano_banana_2_1', 'nano_banana_2_product_placement', 'nano_banana_2_outfit_collage',
    'nano_banana_2_skin_enhancer', 'skin_enhancer', 'nano_banana_2_relight', 'game_dump', 'seedream',
    'seedream_v4_5', 'headshot', 'sync_so', 'concat_videos', 'explainer_video', 'text2keyframes', 'kling_lipsync',
    'wan2_5_video', 'infinite_talk', 'wan2_5_speak', 'sora2_video', 'sora2_video_deflicker', 'sora2_video_upscale',
    'open_sora', 'video_upscale', 'video_deflicker', 'watermark', 'image_overlay', 'maskify', 'keyframes_faceswap',
    'wan_2_2_animate_v3_first_frame', 'wan_2_2_animate_v3_image_picker', 'wan2_2_animate_preview', 'revoice',
    'reve', 'wan2_2_animate_faceswap', 'kling_transition', 'qwen_camera_control', 'link_to_ad_collage',
    'viral_transform_video', 'viral_transform_image', 'clothe_beats', 'beat_fit', 'flux_2', 'flux_2_pro_outpaint',
    'flux_klein_edit', 'model_x', 'sticker_slicer', 'sticker_matchcut', 'video_frame_extractor', 'mixed_media',
    'mixed_media_preview', 'kling_video_edit', 'kling_video_reference', 'kling_omni_flf',
    'kling_omni_image_reference', 'outfit_matchcut', 'kling_omni_image', 'z_image', 'kling2_6', 'kling2_6_lipsync',
    'nano_banana_2_ai_stylist', 'maskify_v2', 'character_swap_v2', 'nano_banana_2_upscale', 'nano_banana_2_shots',
    'nano_banana_2_zooms', 'wan2_6', 'cinematic_studio_image', 'openai_hazel', 'openai_hazel_mini', 'imagegen_2_0',
    'gpt_image_2', 'gpt_image_2_5', 'gpt_image_2_6', 'gpt_image_2_6_flare', 'gif', 'mockup_studio',
    'cinematic_studio_video', 'kling2_6_motion_control', 'kling3_0_motion_control', 'seedance1_5', 'next_shots',
    'outpaint', 'ai_influencer', 'cinematic_studio_image_grid', 'vibe_motion_code2animation',
    'vibe_motion_code2video', 'grok_video', 'grok_video_v15', 'grok_video_v15_lite', 'grok_video_edit',
    'grok_image', 'grok_image_2_0', 'muse_image', 'bytedance_video_upscale', 'bytedance_image_upscale', 'fps_boost',
    'kling_o3_image_reference', 'kling_o3_flf', 'kling3_0', 'kling3_0_turbo', 'kling4_0', 'kling_4_0_flash',
    'kling_image_4_0', 'cinematic_studio_video_v2', 'cinematic_studio_image_3d',
    'cinematic_studio_image_3d_recomposition', 'image_auto', 'seedream_v5_lite', 'seedream_5_0_flash',
    'seedream_5_5', 'seedream_v5_pro', '3d_jutsu_angles', 'seedream_v5_pro_layer_separation', 'text2speech_v2',
    'voice_change', 'voice_change_create_voice', 'voice_change_extract_audio', 'voice_change_separate',
    'voice_change_transform', 'voice_change_merge', 'dubbing', 'dubbing_extract_audio', 'dubbing_lipsync',
    'ip_detection', 'soul_cast', 'soul_cast_edit', 'soul_location', 'soul_location_edit', 'cinematic_studio_2_5',
    'cinematic_studio_2_5_edit', 'cinematic_studio_3_0', 'cinematic_studio_3_0_image_edit',
    'cinematic_studio_soul_cast', 'cinematic_studio_soul_location', 'soul_cinema_studio',
    'video_background_remover', 'image_background_remover', 'bd_studio_kling', 'bd_studio_sora2',
    'bd_studio_soul_cast', 'bd_studio_soul_location', 'hf_fnf_video', 'hf_mult_replace_object', 'hf_evolution',
    'hf_mult_motion_control', 'hf_mult_motion_control_flash', 'hf_mult_replace_object_flash',
    'ai_influencer_motion_control_flash', 'ai_influencer_replace_object_flash', 'ai_influencer_motion_control',
    'restyle', 'ai_influencer_replace_object', 'ai_influencer_restyle', 'seedance_2_0', 'seedance_2_5',
    'seedance_2_5_flash', 'seedance_2_5_kling_upscale', 'seedance_2_5_kling_upscale_part', 'ad_multiplier',
    'ad_multiplier_v2', 'ad_multiplier_v2_part', 'seedance_2_5_motion_control', 'video_character_asset', 'intone',
    'draw_to_video', 'remove_object', 'swap_object', 'video_scene_edit', 'reframe', 'reels_studio',
    'reels_studio_clip', 'cutups_studio_clip', 'marketing_studio_video', 'marketing_studio_image',
    'marketing_studio_hook', 'marketing_studio_brand_kit_scrape', 'marketing_studio_brand_kit_agent',
    'marketing_storyboard', 'ms_image', 'seedance_2_0_fast', 'seedance_2_0_mini', 'seedance_unlimited',
    'seedance_mini_unlimited', 'wan2_7', 'wan3_0', 'wan3_0_prime', 'character_sheet', 'cinematic_studio_video_3_5',
    'cinema_studio_3_5_video_edit', 'cinema_studio_4_0', 'cinematic_studio_video_4_0', 'cinematic_video_relight',
    'cinematic_video_inpaint', 'videoshop_relight', 'videoshop_edit', 'videoshop_camera_move', 'videoshop_genjutsu',
    'cinematic_video_editor', 'video_trim', 'video_extract_frames', 'video_splice', 'video_transition_prep',
    'timeline_render', 'video_compress', 'ad_multiplier_replace', 'happy_horse_video', 'gemini_omni',
    'gemini_omni_flash_1_1', 'gemini_omni_flash_1_2', 'magi_2', 'sam_3_video', 'sam_3_3d', 'sam_3_3d_body',
    'image_decompose', 'bria_eraser', 'image_command', 'image_to_3d', 'multi_image_to_3d', '3d_rigging', 'tripo_3d',
    'meshy_v5_remesh', 'meshy_v5_retexture', 'meshy_v7_image_to_3d', 'tripo_p2_image_to_3d',
    'tripo_h3_1_image_to_3d', 'tripo_h3_1_multiview_to_3d', 'hunyuan3d_v3_image_to_3d', 'meshy_v6_text_to_3d',
    'hunyuan3d_v3_1_text_to_3d', 'llm_text', 'image_text_detection', 'brain_activity', 'recraft_v4_1',
    'recraft_v4_styles', 'color_grading_lut', 'clipify', 'clip_transcriber', 'elevenlabs_music_v1',
    'elevenlabs_music_v2', 'elevenlabs_music_v2_5', 'sonilo_music', 'mirelo_text_to_audio',
    'inworld_text_to_speech', 'seed_audio', 'qwen_audio_tts', 'elevenlabs_v4', 'audio_dubbing',
    'elevenlabs_video_to_music', 'elevenlabs_v4_turbo', 'autosprite', 'nano_banana_pro_unlimited',
    'gpt_image_2_unlimited', 'kling_3_unlimited', 'seedance_2_unlimited', 'speech2text', 'video2text',
    'video_explainer', 'katana_preset_v1', 'what_if_v1', 'what_if_result', 'ads_story_result', 'ai_reels_v1',
    'drama_episode_edit', 'dramas_v1', 'music_cards_v1', 'ai_reels_result', 'short_drama_result',
    'music_cards_result', 'youtube_faceless_video', 'ai_host_video', 'playable_ads_agent_v1', 'realtor_studio_v1',
    'realtor_studio_video', 'realtor_studio_still', 'realtor_studio_render_still', 'realtor_studio_voice',
    'ai_host_render', 'higgsfield_hdr_video', 'mobilecontent_studio_pasteup', 'depth_anything_video',
    '3d_camera_track', 'kimodo', 'ads_studio_creative', 'ads_studio_edit', 'p_image_ideogram', 'ideogram_4_6',
    'ideogram_4_6_precise_edit', 'ideogram_4_5', 'ideogram_4_5_precise_edit', 'ideogram_vector',
    'video_split_frames', 'video_stitch_frames', 'video_over_image', 'viral_hub_video', 'viral_hub_rendered_image',
    'viral_hub_rendered_video',
})
