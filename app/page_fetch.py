"""Bounded, DNS-pinned HTML GETs. No browser, JS, subresources, cookies or form submission."""
import asyncio
import socket
from urllib.parse import unquote, urljoin, urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver

from app.config import tls_context
from app.security import DOWNLOADS, parse_url, public_ip, resolve

MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 3
TOTAL_TIMEOUT = 18
BINARY_SUFFIXES = DOWNLOADS + (".zip", ".7z", ".rar", ".pdf", ".png", ".jpg", ".jpeg")
REDIRECT_CODES = {301, 302, 303, 307, 308}


class PinnedResolver(AbstractResolver):
    def __init__(self, hostname, addresses):
        if not addresses or any(not public_ip(ip) for ip in addresses):
            raise ValueError("Non-public address")
        self.hostname = hostname
        self.addresses = tuple(addresses)

    async def resolve(self, host, port=0, family=socket.AF_UNSPEC):
        if host.rstrip(".").lower() != self.hostname:
            raise OSError("Unexpected hostname")
        return [{"hostname": host, "host": ip, "port": port,
                 "family": socket.AF_INET6 if ":" in ip else socket.AF_INET,
                 "proto": 0, "flags": socket.AI_NUMERICHOST} for ip in self.addresses]

    async def close(self):
        pass


async def request_html(url, hostname, port, addresses, *, headers_only=False):
    """Return headers/body only; caller manually validates every redirect."""
    connector = aiohttp.TCPConnector(
        resolver=PinnedResolver(hostname, addresses), use_dns_cache=False,
        force_close=True, limit=1, ssl=tls_context(),
    )
    async with aiohttp.ClientSession(
        connector=connector, cookie_jar=aiohttp.DummyCookieJar(), trust_env=False,
        auto_decompress=False, timeout=aiohttp.ClientTimeout(total=8, sock_connect=4, sock_read=4),
        headers={"User-Agent": "QRAlert-SecurityPreview/1.0", "Accept": "text/html,application/xhtml+xml",
                 "Accept-Encoding": "identity"},
        max_line_size=8190, max_field_size=8190,
    ) as client:
        async with client.get(url, allow_redirects=False) as response:
            headers = response.headers
            metadata = {"http_status": response.status}
            if response.status in REDIRECT_CODES:
                return {**metadata, "location": headers.get("Location")}
            if headers_only:
                # Close the response without reading the body, including attachments/binary data.
                if not 200 <= response.status < 300:
                    return {**metadata, "status": "unknown", "reason": "정상 응답이 아니므로 최종 주소 확인을 완료하지 못했습니다."}
                return {**metadata, "status": "ok", "bytes_read": 0,
                        "download_response": "attachment" in headers.get("Content-Disposition", "").lower()}
            if response.status != 200:
                return {**metadata, "status": "unknown", "reason": "페이지가 정상 HTML 응답을 반환하지 않았습니다."}
            if "attachment" in headers.get("Content-Disposition", "").lower():
                return {**metadata, "status": "not_applicable", "reason": "첨부 파일 응답이므로 본문을 읽지 않았습니다.",
                        "download_response": True}
            if headers.get("Content-Type", "").split(";", 1)[0].strip().lower() not in {"text/html", "application/xhtml+xml"}:
                return {**metadata, "status": "not_applicable", "reason": "HTML 응답이 아니므로 본문을 읽지 않았습니다."}
            if headers.get("Content-Encoding", "identity").lower().strip() != "identity":
                return {**metadata, "status": "unknown", "reason": "압축 응답은 분석하지 않습니다."}
            length = headers.get("Content-Length")
            if length and (not length.isdecimal() or int(length) > MAX_BYTES):
                return {**metadata, "status": "unknown", "reason": "페이지 크기가 분석 한도를 초과합니다."}
            data = bytearray()
            async for chunk in response.content.iter_chunked(16384):
                if len(data) + len(chunk) > MAX_BYTES:
                    return {**metadata, "status": "unknown", "reason": "페이지 크기가 분석 한도를 초과합니다."}
                data.extend(chunk)
            encoding = response.charset or "utf-8"
            try:
                html = bytes(data).decode(encoding, errors="replace")
            except LookupError:
                html = bytes(data).decode("utf-8", errors="replace")
            return {**metadata, "status": "ok", "html": html, "bytes_read": len(data)}


async def fetch_page(url, *, headers_only=False):
    async def follow():
        current = url
        chain = []
        seen = set()
        for hop in range(MAX_REDIRECTS + 1):
            try:
                normalized, host, scheme, port = parse_url(current)
            except ValueError:
                return {"status": "blocked", "reason": "지원하지 않는 이동 주소입니다.", "redirect_chain": chain}
            # Fragments are client-only and are never sent to the target.
            parsed = urlsplit(normalized)
            normalized = parsed._replace(fragment="").geturl()
            if normalized in seen:
                return {"status": "unknown", "reason": "반복 리디렉션입니다.", "redirect_chain": chain}
            seen.add(normalized)
            dns = await resolve(host, port)
            if dns["status"] != "ok":
                return {"status": dns["status"], "reason": dns.get("reason", "DNS 확인 실패"),
                        "redirect_chain": chain}
            if unquote(parsed.path).lower().endswith(BINARY_SUFFIXES):
                return {"status": "not_applicable", "reason": "파일 경로는 요청하지 않습니다.",
                        "final_url": normalized, "redirect_chain": chain}
            if headers_only:
                response = await request_html(normalized, host, port, dns["addresses"], headers_only=True)
            else:
                response = await request_html(normalized, host, port, dns["addresses"])
            chain.append({"url": normalized, "http_status": response["http_status"]})
            if response["http_status"] not in REDIRECT_CODES:
                return {**response, "final_url": normalized, "redirect_chain": chain}
            if hop == MAX_REDIRECTS:
                return {"status": "unknown", "reason": "리디렉션 횟수 제한을 초과했습니다.", "redirect_chain": chain}
            location = response.get("location")
            if not location:
                return {"status": "unknown", "reason": "이동 주소가 없는 리디렉션입니다.", "redirect_chain": chain}
            # Resolve relative Location but validate raw controls BEFORE urljoin can strip them.
            if len(location) > 4096 or any(ord(c) < 33 for c in location) or "\\" in location:
                return {"status": "blocked", "reason": "잘못된 이동 주소입니다.", "redirect_chain": chain}
            next_url = urljoin(normalized, location)
            if scheme == "https" and urlsplit(next_url).scheme.lower() == "http":
                return {"status": "blocked", "reason": "HTTPS에서 HTTP로의 이동을 차단했습니다.", "redirect_chain": chain}
            current = next_url

    try:
        return await asyncio.wait_for(follow(), TOTAL_TIMEOUT)
    except (aiohttp.ClientError, OSError, TimeoutError, ValueError):
        return {"status": "unknown", "reason": "제한 시간 내 페이지를 안전하게 가져오지 못했습니다.", "redirect_chain": []}
