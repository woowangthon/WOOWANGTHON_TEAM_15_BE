# 사진 QR 디코딩

POST /api/qr/decode

입력은 JSON {"image_base64": "..."}입니다. JPG/PNG/WebP, 디코딩된 파일 3MiB 이하,
이미지 1,600만 픽셀 이하로 제한합니다. 프론트 QR 업로드는 최대 긴 변 3200px JPEG를 준비합니다.

정상 응답:
~~~json
{"status":"ok","qr_text":"https://naver.com","decoder":"zxing_cpp","auto_open":false,"message":"서버에서 QR을 읽었어요. 주소는 열지 않았어요."}
~~~

QR 미검출: HTTP 200, status=not_found, qr_text=null.
서로 다른 QR 여러 개: HTTP 200, status=multiple_qr, qr_text=null. 임의 주소를 선택하지 않습니다.
사진 형식/해상도 오류: HTTP 422. 요청 본문 크기 초과: HTTP 413. 동시 처리 제한: HTTP 503.

zxing-cpp로 QR 데이터를 읽으며 AI 모델이나 외부 사이트를 호출하지 않습니다.
메모리에서 처리하고 사진·QR 내용을 파일이나 로그로 저장하지 않습니다.
휴대폰 디코딩이 실패하고 사용자가 사진 인식을 켠 경우에만 서버 사진 검사를 시도합니다.
동의를 끈 경우에는 사진을 업로드하지 않습니다. 정상 디코딩 후 기존 상표 확인·URL 분석 흐름을 진행합니다.
QR 문자 인식 성공은 주소의 안전 판정이 아니며 HTTP(S) 여부는 다음 단계에서 검사합니다.

설치:
~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
~~~

검증: tests/test_qr_decode.py는 실제 생성한 네 URL의 QR을 포스터에 넣고 JPEG 압축,
회전, 한쪽 배치를 검사합니다. 실행 중인 8000번 백엔드에도 실제 프론트 decodeQRImage 및
scanWithFallback으로 네 포스터를 보내 각각 정확한 원본 주소를 반환하는 것을 확인했습니다.
사용자가 촬영한 문제 사진 및 휴대폰 네이티브 카메라 자체는 직접 검사하지 못했습니다.
