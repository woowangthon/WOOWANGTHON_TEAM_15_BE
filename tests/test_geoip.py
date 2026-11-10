import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.config import PROJECT_ROOT, geoip_database_path
from app.security import country_check


class GeoIPTests(unittest.TestCase):
    def reader(self, countries):
        reader = MagicMock()
        reader.__enter__.return_value = reader
        reader.metadata.return_value = SimpleNamespace(database_type="GeoLite2-Country", build_epoch=1700000000)
        reader.get.side_effect = lambda ip: countries.get(ip)
        return reader

    def test_path_is_relative_to_repository_not_working_directory(self):
        with patch.dict(os.environ, {"GEOIP_DB_PATH": "./data/GeoLite2-Country.mmdb"}):
            self.assertEqual(geoip_database_path(), (PROJECT_ROOT / "data/GeoLite2-Country.mmdb").resolve())

    def test_missing_config_returns_unknown(self):
        with patch.dict(os.environ, {"GEOIP_DB_PATH": ""}):
            self.assertEqual(country_check(["8.8.8.8"])["status"], "unknown")

    def test_domestic_and_overseas_are_information_not_risk(self):
        for code, overseas in [("KR", False), ("US", True)]:
            with self.subTest(code=code), patch.dict(os.environ, {"GEOIP_DB_PATH": "test.mmdb"}), patch("maxminddb.open_database", return_value=self.reader({"8.8.8.8": {"country": {"iso_code": code}}})):
                result = country_check(["8.8.8.8"])
                self.assertEqual(result["status"], "ok")
                self.assertEqual(result["is_overseas"], overseas)
                self.assertEqual(result["countries"][0]["is_overseas"], overseas)
                self.assertTrue(result["database_updated_at"])

    def test_missing_country_and_empty_addresses_are_not_success(self):
        with patch.dict(os.environ, {"GEOIP_DB_PATH": "test.mmdb"}), patch("maxminddb.open_database", return_value=self.reader({})):
            for addresses in [[], ["8.8.8.8"]]:
                result = country_check(addresses)
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["is_overseas"])

    def test_mixed_location_does_not_claim_single_country(self):
        records = {"8.8.8.8": {"country": {"iso_code": "KR"}}, "1.1.1.1": {"country": {"iso_code": "US"}}}
        with patch.dict(os.environ, {"GEOIP_DB_PATH": "test.mmdb"}), patch("maxminddb.open_database", return_value=self.reader(records)):
            result = country_check(list(records))
            self.assertEqual(result["status"], "ok")
            self.assertIsNone(result["is_overseas"])

    def test_invalid_database_and_wrong_database_type(self):
        with patch.dict(os.environ, {"GEOIP_DB_PATH": "missing.mmdb"}), patch("maxminddb.open_database", side_effect=OSError):
            self.assertEqual(country_check(["8.8.8.8"])["status"], "unknown")
        reader = self.reader({})
        reader.metadata.return_value.database_type = "GeoLite2-ASN"
        with patch.dict(os.environ, {"GEOIP_DB_PATH": "asn.mmdb"}), patch("maxminddb.open_database", return_value=reader):
            self.assertEqual(country_check(["8.8.8.8"])["status"], "unknown")
