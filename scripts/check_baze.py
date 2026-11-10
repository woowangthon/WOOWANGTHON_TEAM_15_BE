"""Verify gateway authentication without printing the key or generating AI content."""
import sys
from urllib.parse import urlsplit

import httpx

from app.config import baze_settings


def main():
    settings = baze_settings()
    if not settings["api_key"]:
        print("BAZE_API_KEY is missing. Set it in the backend .env file.")
        return 1
    parsed = urlsplit(settings["base_url"])
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        print("BAZE_BASE_URL must be an HTTPS base URL without credentials, query or fragment.")
        return 1
    try:
        response = httpx.get(
            settings["base_url"] + "/models/",
            headers={"Authorization": "Bearer " + settings["api_key"]},
            timeout=15, follow_redirects=False, trust_env=False,
        )
        if response.status_code != 200:
            print(f"Gateway authentication check: HTTP {response.status_code}")
            if response.status_code == 401:
                print("Key is invalid or belongs to a different BAZE deployment.")
            return 1
        payload = response.json()
        entries = payload.get("data", payload.get("models", [])) if isinstance(payload, dict) else payload
        models = [item.get("id") for item in entries if isinstance(item, dict) and isinstance(item.get("id"), str)]
        if not models:
            print("HTTP 200 received, but no recognizable model list was returned.")
            return 1
        print(f"Gateway connected. Available models: {len(models)}")
        for model in models[:20]:
            # Output only model IDs; never response headers, tokens or arbitrary error bodies.
            if len(model) <= 150 and all(c.isalnum() or c in "-._/:" for c in model):
                print("- " + model)
        return 0
    except (httpx.HTTPError, ValueError, TypeError):
        print("Gateway check failed: network error or invalid model-list response.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
