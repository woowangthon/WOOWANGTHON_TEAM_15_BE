"""Download GeoLite2-Country.mmdb at deploy time (the file is git-ignored and too large for Render secret files).

Needs MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY (free MaxMind account). Without them, or if the download
fails, it prints a note and exits 0: the server still starts and country lookups report "unknown".

    python -m scripts.fetch_geoip
"""
import io
import os
import sys
import tarfile
from pathlib import Path

import httpx

URL = "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz"
TARGET = Path(__file__).resolve().parents[1] / "data" / "GeoLite2-Country.mmdb"


def main():
    account = os.getenv("MAXMIND_ACCOUNT_ID", "").strip()
    key = os.getenv("MAXMIND_LICENSE_KEY", "").strip()
    if not account or not key:
        print("GeoIP: MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY not set, skipping (country lookups will be unknown).")
        return 0
    try:
        # MaxMind answers with a redirect to a separate download host. httpx drops the
        # Authorization header on cross-host redirects (urllib would forward it and get rejected).
        response = httpx.get(URL, auth=(account, key), follow_redirects=True, timeout=60)
        if response.status_code != 200:
            hint = " (check MAXMIND_ACCOUNT_ID / MAXMIND_LICENSE_KEY)" if response.status_code in (401, 403) else ""
            print(f"GeoIP: download failed (HTTP {response.status_code}){hint}, skipping.")
            return 0
        with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
            member = next(m for m in tar.getmembers() if m.isfile() and m.name.endswith(".mmdb"))
            data = tar.extractfile(member).read()
    except Exception as exc:  # never print the key; only the error type
        print(f"GeoIP: download failed ({type(exc).__name__}), skipping.")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    print(f"GeoIP: saved {TARGET.name} ({len(data) // 1024} KB).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
