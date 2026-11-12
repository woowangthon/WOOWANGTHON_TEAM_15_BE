"""Extract redacted, indexed page evidence. Findings are observations, not URL/brand scores."""
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from app.behavior import supported_types
from app.security import DOWNLOADS, parse_url

TEXT_LIMIT = 4000


def redact_text(value):
    value = re.sub(r"https?://[^\s<>]+", "[URL]", value, flags=re.I)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", value)
    value = re.sub(r"\b(?:\d[\s-]?){6,}\b", "[NUMBER]", value)
    return " ".join(value.split())


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.text = []
        self.text_size = 0
        self.forms = []
        self.current_form = None
        self.passwords = 0
        self.downloads = []
        self.meta_refresh = False
        self.has_scripts = False

    def handle_starttag(self, tag, attrs):
        attrs = {name: value or "" for name, value in attrs}
        if tag == "script":
            self.has_scripts = True
        if tag in {"script", "style", "noscript", "template", "iframe", "object"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            self.meta_refresh = True
        if tag == "form":
            self.current_form = {"action": attrs.get("action") or "", "passwords": 0}
            if len(self.forms) < 32:
                self.forms.append(self.current_form)
        if tag == "input" and attrs.get("type", "").lower() == "password":
            self.passwords += 1
            if self.current_form is not None:
                self.current_form["passwords"] += 1
        if tag == "a" and len(self.downloads) < 32:
            href = attrs.get("href") or ""
            try:
                if unquote(urlsplit(href).path).lower().endswith(DOWNLOADS):
                    self.downloads.append(href)
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "form":
            self.current_form = None

    def handle_data(self, data):
        if not self.hidden and self.text_size < TEXT_LIMIT:
            part = data[:TEXT_LIMIT - self.text_size]
            self.text.append(part)
            self.text_size += len(part)


def inspect_html(html, final_url):
    parser = PageParser()
    parser.feed(html)
    parser.close()
    text = redact_text(" ".join(parser.text))[:TEXT_LIMIT]
    evidence = []
    findings = []

    # Bounded excerpts have stable IDs; unknown/invented references are rejected after inference.
    remaining = text
    while remaining:
        end = min(500, len(remaining))
        if end < len(remaining):
            split = remaining.rfind(" ", 0, end)
            if split > 250:
                end = split
        excerpt = remaining[:end].strip()
        remaining = remaining[end:].lstrip()
        if excerpt:
            evidence.append({"id": f"page_text_{len(evidence) + 1}", "kind": "page_text",
                             "text": excerpt, "supports": supported_types(excerpt)})

    def observation(code, message, evidence_id):
        if not any(f["code"] == code for f in findings):
            findings.append({"code": code, "points": 0, "message": message, "evidence_ids": [evidence_id]})

    current_host = urlsplit(final_url).hostname
    for form in parser.forms:
        if not form["passwords"]:
            continue
        evidence_id = f"form_{sum(e['kind'] == 'form' for e in evidence) + 1}"
        description = "비밀번호 입력란이 있는 폼입니다."
        try:
            _, host, scheme, _ = parse_url(urljoin(final_url, form["action"]))
        except ValueError:
            description += " 전송 주소를 해석하지 못했습니다."
        else:
            if host != current_host:
                description += " 다른 호스트로 전송하도록 설정되어 있습니다. 정당한 외부 인증 서비스인지는 확인하지 않았습니다."
                observation("EXTERNAL_CREDENTIAL_FORM", "비밀번호 폼의 전송 호스트가 다릅니다.", evidence_id)
            if scheme == "http":
                description += " 전송 주소는 HTTP입니다."
                observation("INSECURE_CREDENTIAL_FORM", "비밀번호 폼의 전송 주소가 HTTP입니다.", evidence_id)
        evidence.append({"id": evidence_id, "kind": "form", "text": description, "supports": ["credential_theft"]})
        observation("PASSWORD_FORM", "비밀번호 입력란만으로 악성을 판단하지 않습니다.", evidence_id)
    if parser.passwords and not any(e["kind"] == "form" for e in evidence):
        evidence.append({"id": "form_1", "kind": "form", "text": "폼 밖에 비밀번호 입력란이 있습니다.",
                         "supports": ["credential_theft"]})
        observation("PASSWORD_FORM", "비밀번호 입력란만으로 악성을 판단하지 않습니다.", "form_1")
    if parser.passwords and re.search(r"긴급|즉시|정지|urgent|immediately|suspend", text, re.I):
        reference = next((e["id"] for e in evidence if e["kind"] == "page_text"), "form_1")
        observation("URGENT_CREDENTIAL_REQUEST", "비밀번호 입력과 긴급성 문구가 함께 관찰됩니다.", reference)
    if parser.downloads:
        evidence.append({"id": "link_1", "kind": "link", "text": "실행·설치 파일로 보이는 링크가 있습니다. 파일은 요청하지 않았습니다.",
                         "supports": ["unsafe_installation"]})
        observation("PAGE_EXECUTABLE_LINK", "설치 링크만으로 악성을 판단하지 않습니다.", "link_1")
    readable = bool(text or parser.passwords or parser.downloads)
    return {
        "text": text, "evidence": evidence, "findings": findings,
        "password_fields": min(parser.passwords, 100), "meta_refresh": parser.meta_refresh,
        "readable": readable and not (parser.has_scripts and len(text) < 40 and not parser.passwords and not parser.downloads),
        "coverage": "최대 4,000자의 정적 HTML 본문과 폼 구조만 검사했습니다. JavaScript 실행·폼 제출·파일 검사는 수행하지 않습니다.",
    }
