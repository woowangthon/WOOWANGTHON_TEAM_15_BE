# 현재 점수 정책: metadata-v2 / combined-v2

POST /api/analyze는 페이지 AI를 참고 정보로만 사용합니다.
공식 도메인 AI 검색과 상표·인쇄 주소 비교는 기존처럼 점수에 반영합니다.

- score_version: metadata-v2
- score_scope: tls_domain_age
- components.ai_behavior: null (제외됨을 의미하며 완료 조건에 포함하지 않음)
- 루트 score: TLS + 도메인 생성일
- verdict.version: combined-v2
- verdict.score: 루트 구성 점수 + URL/공식 도메인/인쇄 주소/매장 신호, 최대 100
- 앱 표시 점수 및 등급: verdict
- >=50 위험, >=20 주의, 그 미만은 남은 필수 검사 완료 시 낮음 / 미완료 시 확인 불가

페이지 AI가 strong/none/unknown/실패 어느 결과를 반환해도 점수에 더하지 않습니다.
페이지 AI 미완료·읽을 수 없는 HTML·빈 공격 유형 배열도 종합 검사의 미완료 사유가 아닙니다.
페이지 AI 결과는 화면에서 참고로 표시하며, 설명 생성 입력의 page_attacks에서도 제외합니다.
리디렉션 안전 차단·파일 다운로드 HTTP 응답·최종 URL/인증서 등 구조적 관찰은 유지합니다.
공식 도메인 검색·DNS/RDAP/TLS/국가 정보 등 나머지 필수 검사의 미확인은 그대로 남깁니다.

기존 behavior-v1 및 combined-v1 계산 함수는 과거 결과 재현용으로 남깁니다.
현재 공개 API에서는 metadata_only_result를 거쳐 페이지 AI 점수를 제거합니다.
구버전 프론트는 새 점수 정책을 제대로 해석하지 못할 수 있으므로 프론트도 새로고침해야 합니다.

검증:
- tests/test_metadata_policy.py: 페이지 AI 실패가 정상 도메인 판정을 막지 않음,
  강한 페이지 AI가 점수를 더하지 않음, 도메인 불일치 및 메타데이터 미확인은 유지.
- 프론트 tests/verdict.test.ts: 새 정책의 페이지 AI 실패를 참고로 표시하고 등급을 강등하지 않음.
- 사진 옵션은 서버 QR 디코딩을 먼저 수행하고 성공 후 상표 OCR 확인으로 진행.
  예전 사진 촬영 코드도 QR 디코딩에 먼저 성공해야 상표 OCR을 호출했음.
