"""Runtime settings, read from environment variables (and .env for local runs)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "fde-02-llm-applications"
    environment: str = "local"
    log_level: str = "INFO"

    data_dir: str = "data"
    index_dir: str = "index"

    retrieval_mode: str = "hybrid"     # bm25 | dense | hybrid
    embedder: str = ""                 # lsa | mistral; empty = first available in the index
    reranker: str = "lexical"          # none | lexical | llm
    candidates: int = 30
    context_passages: int = 6
    min_coverage: float = 0.2      # tuned on the FinanceBench dev half (ADR-005)
    answer_mode: str = "auto"          # auto (LLM if a key is set) | llm | extractive
    use_tools: bool = True
    route: bool = True                 # resolve company/period to filings before searching
    scope_guard: str = "finance"       # finance | off: decline advice, personal data, unknown
                                       # companies, non-finance questions (ADR-008)
    mask_output_pii: bool = True       # mask personal identifiers in answers (ADR-008)

    llm_provider: str = "mistral"
    llm_role: str = "default"
    llm_providers_file: str = "config/providers.yaml"
    llm_timeout_seconds: float = 60.0

    max_question_chars: int = 2000


@lru_cache
def get_settings() -> Settings:
    return Settings()
