"""Extract bounded HTML text and observable cues; page instructions are untrusted data."""
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

from app.security import DOWNLOADS, parse_url

TEXT_LIMIT = 4000
SIGNAL_POINTS = {
    "PASSWORD_FORM": 0,
    "EXTERNAL_CREDENTIAL_FORM": 25,
    "INSECURE_CREDENTIAL_FORM": 20,
    "URGENT_CREDENTIAL_REQUEST": 15,
    "PAGE_EXECUTABLE_LINK": 35,
}


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

    def handle_starttag(self, tag, attrs):
        attrs = {name: value or "" for name, value in attrs}
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
    findings = []

    def add(code, message):
        if not any(f["code"] == code for f in findings):
            findings.append({"code": code, "points": SIGNAL_POINTS[code], "message": message})

    if parser.passwords:
        add("PASSWORD_FORM", "페이지에 비밀번호 입력란이 있습니다. 이것만으로 악성임을 뜻하지 않습니다.")
    current_host = urlsplit(final_url).hostname
    for form in parser.forms:
        if not form["passwords"]:
            continue
        try:
            target, host, scheme, _ = parse_url(urljoin(final_url, form["action"]))
        except ValueError:
            continue
        if host != current_host:
            add("EXTERNAL_CREDENTIAL_FORM", "비밀번호 폼이 현재 페이지와 다른 호스트로 전송되도록 설정되어 있습니다.")
        if scheme == "http":
            add("INSECURE_CREDENTIAL_FORM", "비밀번호 폼의 전송 주소가 암호화되지 않은 HTTP입니다.")
    if parser.passwords and re.search(r"긴급|즉시|계정.{0,10}(정지|차단)|urgent|immediately|account.{0,12}suspend", text, re.I):
        add("URGENT_CREDENTIAL_REQUEST", "비밀번호 입력란과 긴급·계정 정지 등을 강조하는 문구가 함께 있습니다.")
    if parser.downloads:
        add("PAGE_EXECUTABLE_LINK", "페이지 안에 실행·설치 파일로 보이는 링크가 있습니다. 파일을 요청하지 않았습니다.")
    return {
        "text": text, "findings": findings, "password_fields": min(parser.passwords, 100),
        "meta_refresh": parser.meta_refresh,
        "coverage": "서버가 반환한 정적 HTML 일부만 분석했습니다. JavaScript 실행·폼 제출·파일 검사는 수행하지 않습니다.",
    }
