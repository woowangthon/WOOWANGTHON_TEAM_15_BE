"""Resolve HTTP redirects with the same SSRF and DNS-pinning policy as page inspection."""
from app.page_fetch import fetch_page


async def resolve_url(url):
    fetched = await fetch_page(url, headers_only=True)
    return {
        "status": fetched["status"],
        "reason": fetched.get("reason"),
        "final_url": fetched.get("final_url"),
        "redirect_chain": fetched.get("redirect_chain", []),
        "download_response": fetched.get("download_response", False),
        "body_inspected": False,
        "auto_open": False,
        "requires_confirmation": True,
        "scope": "http_redirects_only",
    }
