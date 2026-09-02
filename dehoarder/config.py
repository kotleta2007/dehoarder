"""Application settings.

All paths, model ids, and tunable thresholds live here so every stage reads
from one place. Values come from `.env` (see `.env.example`) with the
defaults below.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class LanguageModifiers(BaseSettings):
    """Difficulty modifier added for the language of the edition sold."""

    ru: float = 0.0
    en: float = 0.0
    fr: float = 2.0
    de: float = 4.0
    other: float = 4.0


class LinkThresholds(BaseSettings):
    """Edge weights and thresholds for the graph link stage (stage 6)."""

    author_weight: float = 1.0
    series_weight: float = 0.9
    topic_weight: float = 0.6
    publisher_weight: float = 0.2
    shop_weight: float = 0.1
    similarity_min_cosine: float = 0.75
    similarity_offset: float = 0.65
    similarity_top_k: int = 5


class PlanWeights(BaseSettings):
    """Scoring weights and defaults for the balanced lane walk (stage 7)."""

    continuity_weight: float = 3.0
    cross_pollination_weight: float = 2.0
    same_author_penalty: float = 1.0
    shared_topic_penalty: float = 1.0
    default_tolerance: float = 1.0
    default_horizon: int = 30
    beam_width: int = 5
    lookahead: int = 6


class Settings(BaseSettings):
    """Top-level settings, populated from environment / `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Paths
    data_dir: Path = DATA_DIR
    db_path: Path = Path("dehoarder.db")
    thorium_dir: Path = Path.home() / ".config" / "thorium"
    page_cache_dir: Path = Path("page_cache")
    archive_dir: Path = Path("archive")
    shops_file: Path = DATA_DIR / "shops.yaml"
    topics_file: Path = DATA_DIR / "topics.yaml"

    # OpenRouter / LLM
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_strong_model: str = Field(default="z-ai/glm-5.3", alias="LLM_STRONG_MODEL")
    llm_cheap_model: str = Field(default="deepseek/deepseek-v4-flash", alias="LLM_CHEAP_MODEL")
    embedding_model: str = Field(default="qwen/qwen3-embedding-8b", alias="EMBEDDING_MODEL")

    # Fetch scheduler
    default_min_interval_s: float = 2.0
    global_concurrency: int = 4
    backoff_base_s: float = 30.0
    backoff_cap_s: float = 1800.0

    # Server
    port: int = 8765

    # Tunables
    language_modifiers: LanguageModifiers = LanguageModifiers()
    link_thresholds: LinkThresholds = LinkThresholds()
    plan_weights: PlanWeights = PlanWeights()


settings = Settings()
