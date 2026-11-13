# 상표명 OCR API

## 흐름

1. 앱에서 QR 주변의 상표 글자가 포함된 JPEG/PNG 사진을 확보합니다. QR 문자열만으로 사진을 복원할 수 없습니다.
2. `POST /api/ocr/brands/local`에 multipart/form-data의 **image** 파일로 전송합니다.
3. 인식된 브랜드 후보를 사용자가 확인하거나 여러 후보 중 하나를 선택합니다.
4. 확인한 정규 브랜드명을 기존 `/api/analyze`의 `brand_texts`에 넣습니다.

OCR은 글자를 읽습니다. 글자 없는 그림 로고를 분류하거나 브랜드의 진위를 인증하지 않습니다.
현재 앱의 사진 업로드/후보 확인 화면은 별도로 연결해야 합니다.

## 실행 환경 설치

기본 API 의존성:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Windows CPU OCR 의존성:

```powershell
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv\Scripts\python.exe -B -m scripts.setup_ocr --download-models
```

이 명령은 서버에서 사용할 ko/en 모델을 한 번 내려받습니다. 이미지 분석 요청 중에는 모델을 내려받지 않습니다.
모델 파일은 기본 `data/ocr_models`에 저장하며 Git에 포함하지 않습니다.
OCR 모델은 프로세스마다 한 번 로딩해 재사용합니다. CPU 동시 처리는 프로세스당 한 건으로 제한합니다.
OCR 엔진이 설치되지 않았어도 기본 API 의존성이 있으면 서버와 기존 URL 분석은 실행되며 OCR 요청에만 503을 반환합니다.

선택 설정(.env.example 참고):

```dotenv
OCR_MODEL_DIR=./data/ocr_models
OCR_MIN_CONFIDENCE=0.65
```

상대 모델 경로는 프로젝트 루트 기준입니다. 0.65는 초기 필터 기준이며 실제 사진을 평가해 조정해야 합니다.
인식 신뢰도는 글자 읽기의 엔진 출력이며 브랜드 소유·사이트 안전 확률이 아닙니다.
기존 BAZE 키나 별도의 OCR API 키는 필요하지 않습니다.

## 요청

FastAPI `/docs`에서 `POST /api/ocr/brands/local` → Try it out → image 파일 선택 → Execute를 사용할 수 있습니다.

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/ocr/brands/local" -F "image=@C:/Users/User/Desktop/brand.jpg"
```

- 파일 필드명은 image입니다. JSON의 파일 경로나 사진 URL은 받지 않습니다.
- JPEG/PNG, 파일 최대 5MiB, 최대 1,600만 화소를 허용합니다.
- 선언된 Content-Type과 실제 파일 형식이 일치해야 합니다.
- 파일 확장자만 바꾸거나 잘못된 MIME을 지정하면 거부합니다. HEIC/GIF/SVG 대신 JPEG/PNG로 보내세요.
- EXIF 방향 보정 후 RGB로 변환하고 긴 변을 최대 1,600픽셀로 축소합니다.
- HTTP 본문은 multipart 오버헤드를 포함해 5MiB+64KiB로 먼저 제한하며 Content-Length가 없는 업로드도 검사합니다.
- 최대 50개 글자 블록·블록당 200자를 반환합니다. bounding_box 좌표는 processed_width/processed_height로 표시한 보정·축소 이미지 기준입니다.
- 원본 이미지를 영구 보관하지 않습니다. FastAPI multipart 처리 중 임시 파일이 사용될 수 있으며 요청 후 닫습니다.
- 이미지/인식 결과는 BAZE나 의심 사이트로 전송하지 않습니다. 서버 로컬 OCR로 처리합니다.

## 응답 예시

아래 수치는 형식 설명용 예시입니다.

```json
{
  "ocr_status": "ok",
  "texts": [{"text": "STARBUCKS COFFEE", "confidence": 0.95, "bounding_box": [[10,10],[300,10],[300,70],[10,70]]}],
  "brand_candidates": [{"brand": "스타벅스", "matched_text": "STARBUCKS COFFEE", "ocr_confidence": 0.95}],
  "brand_texts": ["스타벅스"],
  "requires_confirmation": true,
  "processed_width": 1000,
  "processed_height": 600,
  "truncated": false,
  "min_confidence": 0.65,
  "note": "OCR 신뢰도는 글자 인식 신뢰도입니다. 브랜드와 사이트의 진위를 보증하지 않습니다. 후보를 확인한 뒤 분석에 사용하세요."
}
```

- ok: 기준 이상인 브랜드가 하나. brand_texts는 **확인 전 제안값**입니다.
- ambiguous: 기준 이상 브랜드가 여러 개. brand_texts=[]이고 후보 중 하나를 선택해야 합니다.
- low_confidence: 브랜드 후보/글자의 신뢰도가 부족함. brand_texts=[]이고 재촬영·수동 확인이 필요합니다.
- no_brand: 글자는 있으나 등록된 브랜드와 일치하지 않음.
- no_text: 읽은 글자가 없음.
- 모든 상태에서 requires_confirmation=true이며 자동으로 위험 점수를 변경하지 않습니다.
- 인식 실패를 안전/공식 브랜드 확인으로 해석하지 않습니다.

사용자가 브랜드를 확인하면 다음과 같이 기존 API에 전달합니다. 이 시점부터 기존 도메인 비교와 종합 판정이 실행됩니다.

```json
{
  "qr_text": "https://www.starbucks.co.kr",
  "brand_texts": ["스타벅스"],
  "inspect_page": true,
  "include_ai": true
}
```

현재 combined-v1은 브랜드 불일치 신호를 종합 점수에 반영하므로, OCR 오인식 결과를 확인 없이 자동 확정해서 보내지 마세요.

## 상태 코드

| 코드 | 의미 |
| --- | --- |
| 400 | 빈 파일·손상된 이미지 |
| 413 | 파일·본문 크기 또는 해상도 초과 |
| 415 | 지원하지 않는 형식·MIME 불일치·애니메이션 |
| 422 | image 필드 누락 |
| 503 | 엔진/모델/브랜드 DB 준비 실패 또는 다른 OCR 처리 중 |
| 504 | 인식 응답 시간 30초 초과 |

503 busy 응답은 Retry-After: 3을 포함합니다. 504로 응답해도 이미 실행된 CPU 작업은 끝날 때까지 잠금을 유지합니다.
요청 타임아웃은 CPU 프로세스를 강제로 중단하는 기능이 아닙니다.

## 브랜드 추가 및 테스트

`app/data/brand_aliases.json`에 정규 브랜드명과 한글·영문 별칭을 추가합니다.
정규 브랜드는 `app/data/official_domains.json`에도 등록되어 있어야 합니다.
영문 대소문자·유니코드 전각·글자 사이 공백은 정리하지만, 비슷한 철자를 임의의 브랜드로 추측하지 않습니다.
이메일·URL만 보고 브랜드를 확정하지 않으며, 같은 브랜드의 중복 인식은 최고 신뢰도 후보 하나로 묶습니다.

로컬 사진 직접 검사(서버 실행·유료 API 호출 없이):

```powershell
.\.venv\Scripts\python.exe -B -m scripts.check_ocr "C:/Users/User/Desktop/brand.jpg"
```

자동 테스트:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_ocr.py -v
```

글자가 선명한 사진, 어두운 사진, 기울어진 사진, 상표 없는 사진, 상표가 여러 개인 사진을 함께 평가하세요.
깨끗한 합성 글자 이미지 인식 성공은 실제 촬영 정확도를 보증하지 않습니다.

## 기존 AI 이미지 인식 API와 구분

CPU OCR은 `POST /api/ocr/brands/local` (multipart image)을 사용합니다.
기존 `POST /api/ocr/brands` (JSON image_base64)은 BAZE 이미지 인식 API로 유지합니다.
서로 다른 요청·응답 형식이므로 프론트에서 혼용하지 않습니다.
