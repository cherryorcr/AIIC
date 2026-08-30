from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "AI Interview Coach API")
    app_env: str = os.getenv("APP_ENV", "development")
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    database_path: Path = Path(
        os.getenv("DATABASE_PATH", str(Path(__file__).resolve().parents[2] / "data" / "app.db"))
    )
    # Set DATABASE_URL to a PostgreSQL DSN in production.  The current
    # challenge runtime keeps SQLite as the zero-config default; migration
    # SQL and an adapter boundary are provided under ``backend/migrations``.
    database_url: str = os.getenv("DATABASE_URL", "")
    database_pool_size: int = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    dataset_path: Path = Path(
        os.getenv(
            "INTERVIEW_DATASET_PATH",
            str(Path(__file__).resolve().parents[2] / "data" / "mock-interview-dataset.json"),
        )
    )

    # 强模型只从环境变量读取密钥，仓库中不保存真实 API key。
    strong_model_base_url: str = os.getenv("STRONG_MODEL_BASE_URL", "https://jojocode.com/v1")
    strong_model_api_key: str = os.getenv("STRONG_MODEL_API_KEY", "")
    strong_model_name: str = os.getenv("STRONG_MODEL_NAME", "gpt-4o-mini")

    # 弱模型通过 OpenAI-compatible 网关访问。默认不主动连接，部署时配置地址即可。
    local_model_base_url: str = os.getenv("LOCAL_MODEL_BASE_URL", "")
    local_model_api_key: str = os.getenv("LOCAL_MODEL_API_KEY", "")
    local_model_name: str = os.getenv("LOCAL_MODEL_NAME", "local-interview")
    model_timeout_seconds: float = float(os.getenv("MODEL_TIMEOUT_SECONDS", "30"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "2"))
    model_retry_backoff_seconds: float = float(os.getenv("MODEL_RETRY_BACKOFF_SECONDS", "0.25"))
    # Cost telemetry is opt-in. Values are USD per 1,000 tokens and default
    # to zero for self-hosted models or unknown third-party pricing.
    strong_model_input_cost_per_1k: float = float(os.getenv("STRONG_MODEL_INPUT_COST_PER_1K", "0"))
    strong_model_output_cost_per_1k: float = float(os.getenv("STRONG_MODEL_OUTPUT_COST_PER_1K", "0"))
    local_model_input_cost_per_1k: float = float(os.getenv("LOCAL_MODEL_INPUT_COST_PER_1K", "0"))
    local_model_output_cost_per_1k: float = float(os.getenv("LOCAL_MODEL_OUTPUT_COST_PER_1K", "0"))
    model_strict: bool = _bool("MODEL_STRICT", False)

    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")
    sandbox_timeout_seconds: float = float(os.getenv("SANDBOX_TIMEOUT_SECONDS", "3"))
    sandbox_max_output_bytes: int = int(os.getenv("SANDBOX_MAX_OUTPUT_BYTES", "20000"))
    sandbox_cpu_seconds: int = int(os.getenv("SANDBOX_CPU_SECONDS", "2"))
    sandbox_memory_mb: int = int(os.getenv("SANDBOX_MEMORY_MB", "256"))
    sandbox_max_processes: int = int(os.getenv("SANDBOX_MAX_PROCESSES", "16"))
    sandbox_max_file_bytes: int = int(os.getenv("SANDBOX_MAX_FILE_BYTES", "1048576"))
    sandbox_enabled: bool = _bool("SANDBOX_ENABLED", True)
    document_max_bytes: int = int(os.getenv("DOCUMENT_MAX_BYTES", str(5 * 1024 * 1024)))
    document_max_text_chars: int = int(os.getenv("DOCUMENT_MAX_TEXT_CHARS", "40000"))


settings = Settings()
