# 점수·AI 판정 점검 (2026-11-14)

이 문서는 공식 도메인 AI 검색 전환 전의 점검 기록입니다. 현재 공식 도메인 판정은 [AI 웹 검색](ai_domain_verification.md)을 사용하므로 아래 정적 DB의 탐지 범위 설명과 구분해서 읽어야 합니다.

## 검증 범위

- 모델: 현재 .env에 설정된 BAZE gpt-6-luna.
- 기본 합성 HTML 10건과 경계 사례 9건을 production inspect_html → assess_content 경로로 검사.
- 합성 HTML만 AI에 전송했으며, 사례에 적힌 URL 방문·JavaScript 실행·폼 제출·파일 실행은 하지 않음.
- 19건 중 읽을 수 없는 JavaScript 화면 1건은 AI 호출 없이 skipped/unknown. 나머지 18건은 실제 AI 응답.
- 이 결과는 작은 합성 표본의 단일 실행 기록이며 실제 서비스 전체 정확도나 무오탐을 보장하지 않음.
- 이번 점검에서 위험 배점·모델·프롬프트를 변경하지 않음.

## 실제 모델 결과

| 그룹 | 건수 | 실제 AI 결과 |
| --- | ---: | --- |
| 기본 정상: 로그인·결제·배포 안내·처리방침·피싱 예방·프롬프트 주입 | 6 | 모두 none, AI 0점 |
| 기본 공격: 비밀번호/OTP·신분증·선입금·보안 해제 설치 | 4 | 해당 유형 strong, AI 60점 |
| 추가 정상: 본인이 요청한 OTP·긴급 피싱 예방문·보안 프로그램 안내 | 3 | 모두 none, AI 0점 |
| 정상 외부 SSO | 1 | credential_theft=weak, AI 10점 |
| JavaScript만 있는 빈 화면 | 1 | skipped/unknown, AI 점수 미산출 |
| 추가 공격: 복구 문구·환불 카드정보·신분증 강요·원격 제어 설치 | 4 | 해당 유형 strong, AI 60점 |

외부 SSO는 기대값 none과 달리 weak를 반환했다. 평가기는 비영점 경고를 모두 양성으로 세므로 FP 1건이다.
단, 강한 위험 판정(60점) 오탐은 관찰되지 않았다. AI 10점만 있고 다른 위험 신호가 없다면 현재 종합 기준은 낮음일 수 있다.
AI 항목의 주의 표시와 종합 등급의 20점 경계를 함께 검토해야 한다.

기본 평가 요약: PASS 10 / FAIL 0 / INCONCLUSIVE 0, TP 4 / TN 6 / FP 0 / FN 0.
경계 평가 요약: PASS 7 / FAIL 1 / INCONCLUSIVE 1, TP 4 / TN 3 / FP 1 / FN 0.
unknown을 정상(TN)으로 집계하지 않는다.

## 유사 상표 점수 점검

대상 사이트에 접속하지 않고 /api/analyze를 TestClient로 실행했다. 외부 도메인·AI 결과는 모의했고,
URL 파싱·유사 상표 탐지·종합 점수·응답 직렬화는 실제 코드로 수행했다.

- nav3r.com / naevr.com / navr.com / starbuks.co.kr: lookalike 탐지, verdict.score=50, verdict.level=위험.
- naver.com / never.com: 유사 상표로 가산하지 않음.
- kaka0.com: 현재 DB에 카카오가 없어 탐지되지 않음. 조회 성공·다른 신호 없음 모의 조건에서 verdict.score=0.
- DB의 실제 상표는 현재 네이버·스타벅스·이디야뿐이다. 별칭과 테스트브랜드 행은 별개 상표로 세지 않음.
- 점수를 올려도 미등록 상표 탐지 누락은 해결되지 않는다. 공식 도메인 DB 확대·검증이 별도로 필요하다.
- API 루트 score는 AI/TLS/생성일만 반영하므로 유사 상표 사례에서도 0일 수 있다.
  화면은 반드시 verdict.score / verdict.level을 사용해야 한다.

## 확인 불가 점수 점검

각각 AI / TLS / 생성일 / 국가를 미확인으로 만든 모의 사례는 known score=0일 수 있지만
verdict.level=확인 불가, verdict.assessment_status=partial이다. 모든 점수 항목이 미측정이면 score=null이다.
이는 unknown에 0점을 부여해 안전하다고 판정한 결과가 아니라, 확인된 신호만 합산한 부분 점수다.

unknown을 악성 가산점과 섞으면 서버 장애나 DB 미설정만으로 악성 판정이 생긴다.
중요 검사가 미완료일 때 숫자보다 확인 불가와 미완료 사유를 우선 표시하는 정책을 유지하고,
별도 불확실성 지표나 접속 권고 정책은 위험 근거 점수와 구분해 정해야 한다.

## 재현

추가 경계 사례는 tests/fixtures/behavior_boundary_cases.json에 저장했다.

~~~powershell
# 오프라인 API·점수·유사 상표 회귀 검사
.\.venv\Scripts\python.exe -B -m unittest tests.test_domain_keywords tests.test_verdict tests.test_behavior tests.test_page_analysis tests.test_behavior_evaluation

# 실제 BAZE 호출: 토큰을 사용하며 결과는 실행마다 달라질 수 있음
.\.venv\Scripts\python.exe -B -m scripts.evaluate_behavior --live
.\.venv\Scripts\python.exe -B -m scripts.evaluate_behavior --cases tests/fixtures/behavior_boundary_cases.json --live
~~~

경계 평가에 FAIL 또는 INCONCLUSIVE가 있으면 종료 코드는 1이다.
이번 실행의 외부 SSO 오탐과 읽을 수 없는 화면을 숨기거나 성공으로 집계하지 않는다.
