"""Pydantic models for the catalog scraper (one per kind) + CatalogDataset.

Conventions: typed common fields, `media: list[MediaRef]` (normalized), `extra: dict` = every API key that is not
mapped to a typed field (so nothing is lost), `source: Provenance`. Timestamps are ISO-8601 UTC.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import AwareDatetime, Field

from ...core.dataset import CoreMeta
from ...schemas.common import Provenance, Strict

MediaType = Literal["image", "video", "audio", "json", "other"]


class MediaRef(Strict):
    role: str = Field(description="preview, preview_thumbnail, preview_optimized, preview_main, widescreen, voice, "
                                  "waveform, image, result, style, input_image, ...")
    url: str
    type: MediaType = Field(description="normalized from extension / content type / API type")
    api_type: Optional[str] = Field(None, description="type as given by the API (video, static, animated, image)")
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    duration_ms: Optional[int] = None
    content_type: Optional[str] = None
    placeholder: Optional[str] = Field(None, description="base64 blur placeholder (only with --keep-placeholders)")
    extra: dict[str, Any] = Field(default_factory=dict)


class _Entity(Strict):
    media: list[MediaRef] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict, description="API keys not mapped to typed fields")
    source: Provenance


class _Preset(_Entity):
    """Shared shape of /motions, /styles and the per-model motion lists."""
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    preset_family: Optional[str] = None
    categories: list[Any] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    priority: Optional[float] = None
    cms_id: Optional[str] = None
    params: Optional[dict[str, Any]] = None
    has_preview: bool = Field(False, description="False when the API returned no usable preview URL")


class MotionMixItem(Strict):
    id: Optional[str] = None
    name: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Motion(_Preset):
    mix: Optional[list[MotionMixItem]] = Field(None, description="member motions of a 'mix' collection")
    is_collection: bool = False
    detail_fetched: bool = Field(False, description="True when /motions/{id} was merged in (--with-details)")


class MotionDetail(_Preset):
    """/motions/{id}; merged into Motion by build_dataset (not a separate collection)."""


class MotionSample(_Entity):
    sample_uid: str = Field(description="<motion_id>:<sample id>")
    id: str
    motion_id: str
    preset_family: Optional[str] = None
    priority: Optional[float] = None


class Style(_Preset):
    pass


class Avatar(_Entity):
    id: str
    name: Optional[str] = None
    voice_id: Optional[str] = None
    input_image_id: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class AvatarPreset(_Entity):
    id: str
    name: Optional[str] = None
    quality: Optional[str] = None
    chunks_count: Optional[int] = None
    params: Optional[dict[str, Any]] = None


class Voice(_Entity):
    id: str
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    categories: list[Any] = Field(default_factory=list)
    is_gpt: Optional[bool] = None
    voice_url: Optional[str] = None
    waveform_url: Optional[str] = None
    image_url: Optional[str] = None


class ReferenceVoice(_Entity):
    id: str
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[str] = None
    voice_type: Optional[str] = Field(None, description="API `type` (preset; user voices are never requested)")
    supported_models: list[str] = Field(default_factory=list)
    audio_url: Optional[str] = Field(None, description="API `source`")
    thumbnail_url: Optional[str] = None
    waveform_url: Optional[str] = None


class Sound(_Entity):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    sound_url: Optional[str] = None
    waveform_url: Optional[str] = None


class SoulSample(_Entity):
    """Pseudonymous: only the API's user_id is kept (no profile/handle)."""
    id: str
    status: Optional[str] = None
    job_set_type: Optional[str] = None
    job_set_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[AwareDatetime] = None
    published_at: Optional[AwareDatetime] = None
    prompt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    seed: Optional[int] = None
    batch_size: Optional[int] = None
    quality: Optional[str] = None
    style_id: Optional[str] = None
    style_name: Optional[str] = None
    style_url: Optional[str] = None
    style_strength: Optional[float] = None
    result_url: Optional[str] = None
    result_type: Optional[str] = None
    params: Optional[dict[str, Any]] = Field(None, description="full generation params (incl. the style object)")


class ViralType(_Entity):
    id: str
    slug: Optional[str] = None
    name: Optional[str] = None
    priority: Optional[float] = None
    lang: Optional[str] = None


class PricePoint(Strict):
    key: str = Field(description="'' = default; else node.param=value,... combination")
    credit_units: Optional[float] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ViralPreset(_Entity):
    id: str
    slug: Optional[str] = None
    preset_kind: Optional[str] = Field(None, description="API `kind` (chain, ...)")
    name: Optional[str] = None
    description: Optional[str] = None
    job_set_type: Optional[str] = None
    duration: Optional[float] = None
    ip_check_required: Optional[bool] = None
    is_main_page: Optional[bool] = None
    priority: Optional[float] = None
    tags: list[Any] = Field(default_factory=list)
    type_ids: list[str] = Field(default_factory=list)
    type_slugs: list[str] = Field(default_factory=list, description="resolved from viral types (if fetched)")
    preview_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    pricing_type: Optional[str] = None
    pricing: Optional[dict[str, Any]] = None
    default_credit_units: Optional[float] = Field(None, description="price_matrix entry with key ''")
    min_credit_units: Optional[float] = None
    max_credit_units: Optional[float] = None
    price_matrix: list[PricePoint] = Field(default_factory=list)
    param_choices: Optional[dict[str, Any]] = None
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    param_inputs: list[Any] = Field(default_factory=list)
    lang: Optional[str] = None


class GenericPreset(_Entity):
    """Login-only catalogs whose exact shape could not be observed without a session: common keys are typed,
    everything else is preserved in `extra`."""
    uid: str = Field(description="<group>:<id> (or id when the catalog has no groups)")
    id: str
    group: Optional[str] = None
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    preset_family: Optional[str] = None
    categories: list[Any] = Field(default_factory=list)
    tags: list[Any] = Field(default_factory=list)
    priority: Optional[float] = None
    cms_id: Optional[str] = None
    params: Optional[Any] = None
    lang: Optional[str] = None


class SoulStyle(GenericPreset):
    style_set: str = Field(description="soul | cinematic | keyframe")


class ModelMotion(GenericPreset):
    model_family: str = Field(description="veo3 | kling | kling2_6 | seedance | wan2_2 | wan2_5 | minimax")


class MarketingPreset(GenericPreset):
    category_id: Optional[str] = None


class KatanaPreset(GenericPreset):
    """fnf-cms-api /katana-presets: GenericPreset + pseudonymous creator keys (the author's username / avatar are
    never stored without --with-profiles; `extra.author` keeps only non-identifying fields)."""
    author_key: Optional[str] = Field(None, description="make_id('creator', author.user_id): same hash as the "
                                                        "showcase/studios author_key / creator_key")
    creator_uid_key: Optional[str] = Field(None, description="core.privacy.creator_uid_key(author.user_id): the "
                                                             "cross-scraper creator key (= author_key)")


# ------------------------------------------------------------------ opt-in extras (2026-11-26)
ENTITY_SCHEMA_VERSION = 1
Credits = Optional[Union[int, float]]


class _OptInEntity(_Entity):
    """Opt-in kinds carry their provenance flat as well (project convention for new items)."""
    source_url: str = Field(description="URL of the API response the record came from")
    scraped_at: AwareDatetime = Field(description="when that response was fetched (UTC)")
    schema_version: int = ENTITY_SCHEMA_VERSION


class ChainPresetInput(Strict):
    id: Optional[str] = None
    type: Optional[str] = Field(None, description="image, ...")
    min: Optional[int] = Field(None, description="properties.min (inputs of this type required)")
    max: Optional[int] = Field(None, description="properties.max")
    properties: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class ChainPreset(_OptInEntity):
    """GET fnf-cms-api/job-set-chain-presets: a one-click chain ("game character creator") with its credit price."""
    id: str = Field(description="API preset id (uuid)")
    product_key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[float] = None
    model: Optional[str] = Field(None, description="underlying video model, e.g. seedance_2_0_fast")
    preset_family: Optional[str] = None
    runtime: Optional[str] = Field(None, description="preset_chain")
    chain_type: Optional[str] = Field(None, description="runtime_params.chain_type")
    runtime_endpoint: Optional[str] = Field(None, description="runtime_params.endpoint (generation POST path)")
    runtime_model: Optional[str] = Field(None, description="runtime_params.model")
    runtime_params: dict[str, Any] = Field(default_factory=dict)
    pricing_mode: Optional[str] = Field(None, description="fixed | dynamic_chain")
    pricing_schema: dict[str, Any] = Field(default_factory=dict)
    cost_credits: Credits = Field(None, description="API cost_credits, in credits (no ÷100, unlike viral "
                                                    "price_matrix credit units). The app shows it as the price, "
                                                    "with discount_credits struck through when they differ")
    discount_credits: Credits = Field(None, description="API discount_credits, in credits: the app shows it alone "
                                                        "when its discount display is off (= regular price)")
    is_discounted: bool = Field(False, description="cost_credits and discount_credits both set and different")
    duration: Optional[float] = None
    inputs: list[ChainPresetInput] = Field(default_factory=list)
    is_hidden: bool = Field(False, description="only in the show_hidden=true list (--include-hidden)")
    has_collaborator: bool = Field(False, description="API `collaborate` is a non-empty creator credit")
    collaborator: Optional[str] = Field(None, description="API `collaborate` (creator credit): --with-profiles only")
    image_preview_url: Optional[str] = None
    lang: Optional[str] = None


class Notice(_OptInEntity):
    """cms.higgsfield.ai/notices: per-model badges/popups (retirements, incidents) and site header bars."""
    id: str = Field(description="hash of section + sorted job_set_types + badge label / header title")
    section: Literal["job_set", "header"]
    job_set_types: list[str] = Field(default_factory=list)
    variant: Optional[str] = Field(None, description="info | warning | ...")
    badge_label: Optional[str] = None
    badge_tooltip: Optional[str] = None
    popup_title: Optional[str] = None
    popup_description: Optional[str] = None
    title: Optional[str] = Field(None, description="header notices: view.title")
    description: Optional[str] = Field(None, description="header notices: view.description")
    link: Optional[str] = Field(None, description="header notices: view.link")
    params: dict[str, Any] = Field(default_factory=dict)
    lang: Optional[str] = None


class RestyleVariant(Strict):
    id: Optional[str] = None
    type: Optional[str] = Field(None, description="edit | original | generation")
    extra: dict[str, Any] = Field(default_factory=dict)


class RestylePreset(_OptInEntity):
    """GET fnf-cms-api/restyle-presets (video restyle styles)."""
    id: str
    name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    preset_source: Optional[str] = Field(None, description="API `source` (higgsfield)")
    job_set_type: Optional[str] = None
    priority: Optional[float] = None
    variants: list[RestyleVariant] = Field(default_factory=list, description="media in `media` (role variant_<type>)")
    image_count: int = 0
    lang: Optional[str] = None


class OutfitCharacter(_OptInEntity):
    """fnf /outfits/characters: the model characters offered by the outfit tool (`--kinds outfit_character`)."""
    id: str = Field(description="API id (uuid; also the image file name)")
    api_type: Optional[str] = Field(None, description="API `type` (media_input)")
    url: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class Page(Strict):
    """One listing response: what the API reported (totals, cursors). Used for totals_available / auditing."""
    page_id: str
    endpoint: str
    catalog: str
    group: Optional[str] = None
    params: dict[str, str] = Field(default_factory=dict)
    first_page: bool
    total: Optional[int] = None
    item_count: int
    next_cursor: Optional[str] = None
    has_more: Optional[bool] = None
    source: Provenance


MODEL_BY_KIND = {
    "catalog_motion": Motion,
    "catalog_motion_sample": MotionSample,
    "catalog_motion_detail": MotionDetail,
    "catalog_avatar": Avatar,
    "catalog_avatar_preset": AvatarPreset,
    "catalog_voice": Voice,
    "catalog_reference_voice": ReferenceVoice,
    "catalog_sound": Sound,
    "catalog_style": Style,
    "catalog_soul_sample": SoulSample,
    "catalog_viral_type": ViralType,
    "catalog_viral_preset": ViralPreset,
    "catalog_soul_style": SoulStyle,
    "catalog_mixed_media_preset": GenericPreset,
    "catalog_model_motion": ModelMotion,
    "catalog_katana_category": GenericPreset,
    "catalog_katana_preset": KatanaPreset,
    "catalog_color_preset": GenericPreset,
    "catalog_youtube_faceless_preset": GenericPreset,
    "catalog_camera_setting": GenericPreset,
    "catalog_marketing_category": GenericPreset,
    "catalog_marketing_preset": MarketingPreset,
    "catalog_chain_preset": ChainPreset,
    "catalog_notice": Notice,
    "catalog_restyle_preset": RestylePreset,
    "catalog_outfit_character": OutfitCharacter,
    "catalog_page": Page,
}

ID_FIELD_BY_KIND = {
    **{k: "id" for k in MODEL_BY_KIND},
    "catalog_motion_sample": "sample_uid",
    "catalog_page": "page_id",
    **{k: "uid" for k, m in MODEL_BY_KIND.items() if issubclass(m, GenericPreset)},
}


# ------------------------------------------------------------------ dataset
class SoulSampleStyle(Strict):
    style_id: str
    name: Optional[str] = None
    url: Optional[str] = None
    samples: int


class Summary(Strict):
    counts: dict[str, int] = Field(default_factory=dict, description="items per kind (short name)")
    totals_available: dict[str, Optional[int]] = Field(default_factory=dict)
    by_category: dict[str, dict[str, int]] = Field(default_factory=dict, description="kind -> category -> items")
    by_model_family: dict[str, dict[str, int]] = Field(default_factory=dict, description="kind -> family -> items")
    login_only: dict[str, str] = Field(default_factory=dict,
                                       description="login-only kind -> fetched | skipped (no session/401) | "
                                                   "not selected")
    motions_without_preview: int = 0
    motions_with_details: int = 0
    soul_sample_styles: list[SoulSampleStyle] = Field(default_factory=list,
                                                      description="Soul styles referenced by the public samples")


class CatalogDataset(Strict):
    schema_version: int = 1
    meta: CoreMeta
    summary: Summary
    motions: list[Motion] = Field(default_factory=list)
    motion_samples: list[MotionSample] = Field(default_factory=list)
    avatars: list[Avatar] = Field(default_factory=list)
    avatar_presets: list[AvatarPreset] = Field(default_factory=list)
    voices: list[Voice] = Field(default_factory=list)
    reference_voices: list[ReferenceVoice] = Field(default_factory=list)
    sounds: list[Sound] = Field(default_factory=list)
    styles: list[Style] = Field(default_factory=list)
    soul_samples: list[SoulSample] = Field(default_factory=list)
    viral_types: list[ViralType] = Field(default_factory=list)
    viral_presets: list[ViralPreset] = Field(default_factory=list)
    soul_styles: list[SoulStyle] = Field(default_factory=list)
    mixed_media_presets: list[GenericPreset] = Field(default_factory=list)
    model_motions: list[ModelMotion] = Field(default_factory=list)
    katana_categories: list[GenericPreset] = Field(default_factory=list)
    katana_presets: list[KatanaPreset] = Field(default_factory=list)
    color_presets: list[GenericPreset] = Field(default_factory=list)
    youtube_faceless_presets: list[GenericPreset] = Field(default_factory=list)
    camera_settings: list[GenericPreset] = Field(default_factory=list)
    marketing_categories: list[GenericPreset] = Field(default_factory=list)
    marketing_presets: list[MarketingPreset] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)


class CatalogDatasetFull(CatalogDataset):
    """CatalogDataset + the opt-in collections. Runs that select none of them keep the exact CatalogDataset
    output (no extra keys, same per-run schema); `schema` export uses this one."""
    chain_presets: list[ChainPreset] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)
    restyle_presets: list[RestylePreset] = Field(default_factory=list)
    outfit_characters: list[OutfitCharacter] = Field(default_factory=list)
