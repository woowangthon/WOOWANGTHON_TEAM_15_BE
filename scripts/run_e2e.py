"""Opt-in live E2E integration: synthetic QR photo, real FE API modules, FastAPI and BAZE.
Makes real AI calls (OCR, page behavior, optional explanation); never opens the QR in a browser.
Native Expo camera, taps and rendering remain manual device checks.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(output):
    import cv2
    from PIL import Image, ImageDraw, ImageFont
    source = "https://httpbin.org/redirect-to?url=https%3A%2F%2Fexample.com"
    qr = cv2.QRCodeEncoder_create().encode(source)
    qr = cv2.copyMakeBorder(qr, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
    qr_image = Image.fromarray(qr).resize((660, 660), Image.Resampling.NEAREST).convert("RGB")
    image = Image.new("RGB", (1100, 1100), "white")
    draw = ImageDraw.Draw(image)
    font = "C:/Windows/Fonts/malgun.ttf"
    draw.text((110, 35), "NAVER", fill="#03a05b", font=ImageFont.truetype(font, 105))
    draw.text((115, 165), "네이버 안내 QR · 테스트용 사진", fill="black", font=ImageFont.truetype(font, 38))
    image.paste(qr_image, (220, 275))
    draw.text((145, 990), "실제 네이버 서비스가 아닌 연결 검사 예시", fill="#555555", font=ImageFont.truetype(font, 32))
    path = output / "naver-redirect-qr.jpg"
    image.save(path, format="JPEG", quality=70)
    image.close()
    qr_image.close()
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(path)))
    if decoded != source:
        raise RuntimeError("Fixture QR could not be decoded")
    fixture = {"image_path": str(path), "decoded_qr": decoded, "expected_brand": "네이버", "expected_final_host": "example.com"}
    target = output / "fixture.json"
    target.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize real network and paid AI calls")
    parser.add_argument("--frontend", type=Path, default=ROOT.parent / "WOOWANGTHON_TEAM_15_FE")
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to run real BAZE calls; this check can consume API credits.")
    frontend = args.frontend.resolve()
    node = shutil.which("node")
    if not node or not (frontend / "scripts/check-e2e.mjs").is_file():
        raise RuntimeError("Node or frontend E2E script is missing")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("Port 8000 is already in use; stop the existing server before this isolated test")
    output = ROOT / "data/ocr_smoke/e2e"
    output.mkdir(parents=True, exist_ok=True)
    fixture = make_fixture(output)
    report = output / "result.json"
    env = os.environ.copy()
    env.pop("EXPO_PUBLIC_API_URL", None)  # The real FE .env must supply its address.
    with (output / "backend.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [sys.executable, "-B", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"],
            cwd=ROOT, env=env, stdout=log, stderr=log,
        )
        try:
            ready = False
            for _ in range(80):
                if server.poll() is not None:
                    raise RuntimeError("Temporary backend failed to start; see data/ocr_smoke/e2e/backend.log")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1) as response:
                        ready = response.status == 200
                    if ready:
                        break
                except OSError:
                    time.sleep(0.25)
            if not ready:
                raise RuntimeError("Backend startup timed out")
            result = subprocess.run([node, "scripts/check-e2e.mjs", str(fixture), str(report)], cwd=frontend, env=env, timeout=150)
            return result.returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
            print("Temporary backend stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
