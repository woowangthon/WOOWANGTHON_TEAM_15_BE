"""Validate the local country database without DNS lookups or paid AI calls."""
import json
import sys

from app.config import geoip_database_path
from app.security import country_check


def main():
    path = geoip_database_path()
    if path is None:
        print("GEOIP_DB_PATH is missing. Set it in the backend .env file.")
        return 1
    print("Database:", path)
    if not path.is_file():
        print("Database file not found. Extract GeoLite2-Country.mmdb and check the path.")
        return 1
    result = country_check(["8.8.8.8"])
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
