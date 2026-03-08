"""Application configuration using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API keys
    OPENAI_API_KEY: str = ""
    FIGMA_ACCESS_TOKEN: str = ""

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # Pipeline tuning
    MAX_FIX_ITERATIONS: int = 5
    MAX_GENERAL_FIX_ITERATIONS: int = 3
    MAX_SPECIALIZED_FIX_ITERATIONS: int = 2
    PIXEL_MISMATCH_THRESHOLD: float = 15.0  # percent; relaxed for cross-engine text rendering
    SSIM_THRESHOLD: float = 0.70

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = ""

    # Directories
    OUTPUT_DIR: str = "./output"
    TEMP_DIR: str = "./temp"

    # OpenAI model settings
    OPENAI_MODEL: str = "gpt-5.2"
    OPENAI_MAX_TOKENS: int = 16384
    OPENAI_TEMPERATURE: float = 0.1

    # Deterministic code generation (bypass GPT-4 for layout)
    USE_DETERMINISTIC_GENERATION: bool = True

    # Chunked code generation (for large designs, only when deterministic=False)
    CHUNK_NODE_THRESHOLD: int = 80
    CHUNK_MAX_NODES_PER_SECTION: int = 40
    CHUNK_MAX_CONCURRENT: int = 3

    def ensure_dirs(self) -> None:
        """Create output and temp directories if they don't exist."""
        Path(self.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.TEMP_DIR).mkdir(parents=True, exist_ok=True)


settings = Settings()
