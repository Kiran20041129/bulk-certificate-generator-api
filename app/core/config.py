"""Application settings, read from environment variables (or a .env file)."""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    template_path: Path
    output_dir: Path
    max_recipients: int
    log_level: str


def _resolve(path_value: str) -> Path:
    """Relative paths are resolved from the project root, not the cwd."""
    path = Path(path_value)
    return path if path.is_absolute() else BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    default_db = f"sqlite:///{(BASE_DIR / 'certificates.db').as_posix()}"
    return Settings(
        database_url=os.getenv("DATABASE_URL", default_db),
        template_path=_resolve(
            os.getenv("TEMPLATE_PATH", "templates/certificate_template.pdf")
        ),
        output_dir=_resolve(os.getenv("OUTPUT_DIR", "generated")),
        max_recipients=int(os.getenv("MAX_RECIPIENTS", "1000")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
