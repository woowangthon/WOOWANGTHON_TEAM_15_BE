
import unittest

from app.services.risk_signals import build_risk_signals


class TestRiskSignals(unittest.TestCase):

    def test_build_risk_signals(self):

        analysis = {
            "url_info": {"valid": True},
            "suspicious_patterns": {"suspicious": False},
            "brand_domain": {"status": "unknown"},
            "store_qr": {
                "status": "matched",
                "is_store_verified": False
            },
            "domain_impersonation": {
                "status": "host_matched"
            },
            "redirect_patterns": {"suspicious": True}
        }

        result = build_risk_signals(analysis)

        self.assertTrue(result["url_valid"])
        self.assertFalse(result["suspicious_url_pattern"])
        self.assertEqual(result["store_qr_status"], "matched")
        self.assertFalse(result["store_data_verified"])
        self.assertTrue(result["redirect_pattern_detected"])


if __name__ == "__main__":
    unittest.main()
