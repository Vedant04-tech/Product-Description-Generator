"""Configuration management for the AI Product Description Generator.

Reads settings from environment variables with sensible defaults.
Centralizes validation thresholds and LLM parameters to prevent magic numbers.
"""

from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import load_dotenv

# Base directory for the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
load_dotenv(dotenv_path=BASE_DIR / ".env")


@dataclass(frozen=True)
class ValidationThresholds:
    """Deterministic validation limits and thresholds."""
    meta_title_min_len: int = 30
    meta_title_max_len: int = 60
    meta_desc_min_len: int = 120
    meta_desc_max_len: int = 160
    bullet_min_count: int = 3
    bullet_max_count: int = 6
    keyword_coverage_warning_ratio: float = 0.5


@dataclass(frozen=True)
class AppConfig:
    """Application and LLM runtime configuration."""
    # LLM Provider: "groq" or "openai"
    llm_provider: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "groq").lower()
    )

    # Groq settings
    groq_api_key: str = field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", "")
    )
    groq_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    )
    groq_temperature: float = field(
        default_factory=lambda: float(os.getenv("GROQ_TEMPERATURE", "0.4"))
    )
    groq_max_tokens: int = field(
        default_factory=lambda: int(os.getenv("GROQ_MAX_TOKENS", "1200"))
    )

    # OpenAI settings (optional alternative)
    openai_api_key: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    openai_temperature: float = field(
        default_factory=lambda: float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
    )

    # Pipeline Settings
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("MAX_RETRIES", "2"))
    )

    # Paths
    base_dir: Path = BASE_DIR
    prompts_dir: Path = BASE_DIR / "prompts"
    data_dir: Path = BASE_DIR / "data"

    # Validation thresholds
    validation: ValidationThresholds = field(
        default_factory=lambda: ValidationThresholds(
            meta_title_min_len=int(os.getenv("META_TITLE_MIN_LEN", "30")),
            meta_title_max_len=int(os.getenv("META_TITLE_MAX_LEN", "60")),
            meta_desc_min_len=int(os.getenv("META_DESC_MIN_LEN", "120")),
            meta_desc_max_len=int(os.getenv("META_DESC_MAX_LEN", "160")),
            bullet_min_count=int(os.getenv("BULLET_MIN_COUNT", "3")),
            bullet_max_count=int(os.getenv("BULLET_MAX_COUNT", "6")),
            keyword_coverage_warning_ratio=float(
                os.getenv("KEYWORD_COVERAGE_WARNING_RATIO", "0.5")
            ),
        )
    )

    def is_api_configured(self) -> bool:
        """Check if at least one LLM provider key is populated with a real key."""
        if self.llm_provider == "groq":
            return bool(self.groq_api_key and self.groq_api_key != "your_groq_api_key_here")
        elif self.llm_provider == "openai":
            return bool(self.openai_api_key and self.openai_api_key != "your_openai_api_key_here")
        return bool(
            (self.groq_api_key and self.groq_api_key != "your_groq_api_key_here")
            or (self.openai_api_key and self.openai_api_key != "your_openai_api_key_here")
        )


config = AppConfig()
