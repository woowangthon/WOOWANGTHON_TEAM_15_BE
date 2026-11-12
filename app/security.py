"""Domain/TLS/IP evidence collection. Page HTTP fetching lives in page_fetch.py."""
import asyncio
import ipaddress
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
import maxminddb
import tldextract

from app.config import geoip_database_path
from app.scoring import score_metadata

EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
TIMEOUT = 5
_bootstrap_cache = None
DOWNLOADS = (".apk", ".exe", ".msi", ".bat", ".cmd", ".scr", ".ps1", ".dmg")


def parse_url(text):
    raw = text.strip()
    if any(ord(c) < 33 for c in raw) or "\\" in raw:
        raise ValueError("공백, 제어 문자, 역슬래시가 없는 HTTP(S) URL을 입력하세요.")
    try:
        parts = urlsplit(raw)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError()
        if parts.username is not None or parts.password is not None:
            raise ValueError()
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parts.port
        if port not in (None, 80, 443):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            import re
            if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in host.split(".")):
                raise ValueError()
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        normalized = urlunsplit((parts.scheme.lower(), authority, parts.path, parts.query, parts.fragment))
        return normalized, host, parts.scheme.lower(), port or (443 if parts.scheme.lower() == "https" else 80)
    except (ValueError, UnicodeError):
        raise ValueError("HTTP(S) URL만 지원합니다. 사용자 정보와 80/443 이외 포트는 허용하지 않습니다.") from None


def public_ip(value):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address in ipaddress.ip_network("64:ff9b::/96"):
        return False
    return address.is_global and not address.is_multicast and not (
        isinstance(address, ipaddress.IPv6Address) and (address.ipv4_mapped or address.sixtofour or address.teredo)
    )


async def resolve(host, port):
    try:
        records = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM), TIMEOUT
        )
        addresses = sorted({r[4][0] for r in records})
        if not addresses or any(not public_ip(ip) for ip in addresses):
            return {"status": "blocked", "addresses": [], "reason": "내부·예약 IP 또는 혼합 DNS 응답은 검사하지 않습니다."}
        return {"status": "ok", "addresses": addresses}
    except (OSError, TimeoutError, ValueError):
        return {"status": "unknown", "addresses": [], "reason": "DNS 조회 실패"}


async def tls_check(host, ip, port):
    writer = None
    try:
        # Connect to the previously validated IP; retain original hostname for SNI/verification.
        _, writer = await asyncio.wait_for(asyncio.open_connection(
            ip, port, ssl=ssl.create_default_context(), server_hostname=host,
            ssl_handshake_timeout=TIMEOUT), TIMEOUT + 1)
        tls = writer.get_extra_info("ssl_object")
        cert = tls.getpeercert()
        expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
        issuer = dict(item for group in cert.get("issuer", ()) for item in group).get("organizationName")
        return {"status": "ok", "valid": True, "expires_at": expires.isoformat(),
                "expires_in_days": max(0, (expires - datetime.now(timezone.utc)).days),
                "checked_ip": ip, "protocol": tls.version(), "issuer": issuer}
    except ssl.SSLCertVerificationError:
        return {"status": "invalid", "valid": False, "reason": "인증서 만료·신뢰 체인·호스트명 검증 실패"}
    except (OSError, TimeoutError, ssl.SSLError):
        return {"status": "unknown", "valid": None, "reason": "TLS 연결 실패"}
    finally:
        if writer:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 1)
            except (OSError, TimeoutError):
                pass


async def rdap_check(host):
    global _bootstrap_cache
    try:
        ipaddress.ip_address(host)
        return {"status": "not_applicable", "reason": "IP 주소에는 도메인 생성일이 없습니다."}
    except ValueError:
        pass
    domain = EXTRACT(host).top_domain_under_public_suffix
    if not domain:
        return {"status": "unknown", "reason": "등록 도메인을 확인할 수 없습니다."}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, trust_env=False) as client:
            if _bootstrap_cache and _bootstrap_cache[0] > time.monotonic():
                services = _bootstrap_cache[1]
            else:
                bootstrap = await client.get("https://data.iana.org/rdap/dns.json")
                bootstrap.raise_for_status()
                services = bootstrap.json()["services"]
                if not isinstance(services, list):
                    raise ValueError("Invalid bootstrap")
                _bootstrap_cache = (time.monotonic() + 3600, services)
            bases = [base for tlds, urls in services
                     if domain.rsplit(".", 1)[-1] in tlds for base in urls
                     if isinstance(base, str) and base.startswith("https://")]
            if not bases:
                return {"status": "unknown", "domain": domain, "reason": "해당 TLD의 RDAP 미지원"}
            response = await client.get(bases[0].rstrip("/") + "/domain/" + domain)
            response.raise_for_status()
            payload = response.json()
            dates = []
            for event in payload.get("events", []):
                if not isinstance(event, dict) or event.get("eventAction") != "registration":
                    continue
                try:
                    created = datetime.fromisoformat(event["eventDate"].replace("Z", "+00:00"))
                    if created.tzinfo is not None and created <= datetime.now(timezone.utc):
                        dates.append(created)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
            if not dates:
                raise ValueError("Missing registration date")
            created = min(dates)
            return {"status": "ok", "domain": domain, "created_at": created.isoformat(),
                    "age_days": (datetime.now(timezone.utc) - created).days}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return {"status": "unknown", "domain": domain, "reason": "RDAP 생성일 조회 실패 또는 응답 누락"}


def country_check(addresses):
    path = geoip_database_path()
    unknown = {"status": "unknown", "countries": [], "is_overseas": None}
    if path is None:
        return {**unknown, "reason": "GEOIP_DB_PATH 국가 DB 설정 필요"}
    if not addresses:
        return {**unknown, "reason": "조회할 공인 IP가 없습니다."}
    try:
        with maxminddb.open_database(str(path)) as reader:
            metadata = reader.metadata()
            if metadata.database_type not in {"GeoLite2-Country", "GeoIP2-Country", "GeoLite2-City", "GeoIP2-City"}:
                return {**unknown, "reason": "Country 또는 City 형식의 국가 DB가 필요합니다."}
            countries = []
            for ip in addresses:
                record = reader.get(ip) or {}
                code = record.get("country", {}).get("iso_code")
                countries.append({"ip": ip, "country_code": code,
                                  "is_overseas": code != "KR" if code else None})
        complete = all(c["country_code"] for c in countries)
        locations = {c["is_overseas"] for c in countries}
        result = {
            "status": "ok" if complete else "unknown",
            "countries": countries,
            "is_overseas": next(iter(locations)) if complete and len(locations) == 1 else None,
            "database_updated_at": datetime.fromtimestamp(metadata.build_epoch, timezone.utc).isoformat(),
            "note": "한국(KR) 기준 서버 위치 추정치이며 운영자 국적·악성 여부를 뜻하지 않습니다.",
        }
        if not complete:
            result["reason"] = "일부 IP의 국가가 DB에 없습니다."
        return result
    except (OSError, ValueError, TypeError, OverflowError, maxminddb.InvalidDatabaseError):
        return {**unknown, "reason": "국가 DB 조회 실패. 파일 경로와 형식을 확인하세요."}


def score_result(url, host, evidence):
    # Host/URL pattern and brand scoring belongs to task 2.
    return score_metadata(url, evidence)


async def analyze_url(text):
    url, host, scheme, port = parse_url(text)
    dns = await resolve(host, port)
    unknown = {"status": "unknown", "reason": "DNS 검사 미완료로 조회하지 않았습니다."}
    evidence = {"dns": dns, "rdap": dict(unknown), "tls": dict(unknown), "geoip": dict(unknown)}
    if dns["status"] == "ok":
        async def rdap_bounded():
            try:
                return await asyncio.wait_for(rdap_check(host), 12)
            except TimeoutError:
                return {"status": "unknown", "reason": "RDAP 전체 시간 제한 초과"}
        async def tls_optional():
            if scheme == "http":
                return {"status": "not_applicable", "valid": None, "reason": "HTTP URL"}
            return await tls_check(host, dns["addresses"][0], port)
        evidence["rdap"], evidence["tls"] = await asyncio.gather(rdap_bounded(), tls_optional())
        evidence["geoip"] = await asyncio.to_thread(country_check, dns["addresses"])
    return {"url": url, "hostname": host, "evidence": evidence, **score_result(url, host, evidence)}
