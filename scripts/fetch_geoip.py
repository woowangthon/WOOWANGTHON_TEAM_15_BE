"""Download GeoLite2-Country.mmdb at deploy time (the file is git-ignored and too large for Render secret files).

Needs MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY (free MaxMind account). Without them, or if the download
fails, it prints a note and exits 0: the server still starts and country lookups report "unknown".

    python -m scripts.fetch_geoip
"""
import base64
import io
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

URL = "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz"
TARGET = Path(__file__).resolve().parents[1] / "data" / "GeoLite2-Country.mmdb"


def main():
    account = os.getenv("MAXMIND_ACCOUNT_ID", "").strip()
    key = os.getenv("MAXMIND_LICENSE_KEY", "").strip()
    if not account or not key:
        print("GeoIP: MAXMIND_ACCOUNT_ID/MAXMIND_LICENSE_KEY not set, skipping (country lookups will be unknown).")
        return 0
    token = base64.b64encode(f"{account}:{key}".encode()).decode()
    request = urllib.request.Request(URL, headers={"Authorization": "Basic " + token})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            archive = response.read()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
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
