"""Load backend-local configuration without overriding deployment environment variables."""
import os
import ssl
from pathlib import Path

import certifi
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


def tls_context():
    # Use Mozilla's CA bundle instead of the OS store. On Windows, Python only sees roots that
    # Windows has already downloaded, so valid sites (e.g. example.com, bit.ly) failed verification
    # and were scored as INVALID_TLS (+25) on some machines.
    return ssl.create_default_context(cafile=certifi.where())


def geoip_database_path():
    value = os.getenv("GEOIP_DB_PATH", "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()
