"""Load backend-local configuration without overriding deployment environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def baze_settings():
    # Read lazily so tests and deployment variables can supply their own values.
    return {
        "api_key": os.getenv("BAZE_API_KEY", "").strip(),
        "base_url": os.getenv(
            "BAZE_BASE_URL", "https://factchat-cloud.mindlogic.ai/v1/gateway"
        ).strip().rstrip("/"),
        "model": os.getenv("BAZE_MODEL", "").strip(),
    }


def geoip_database_path():
    value = os.getenv("GEOIP_DB_PATH", "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
