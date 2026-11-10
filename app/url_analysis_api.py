
# URL 분석 독립 실행용 FastAPI 서버

from fastapi import FastAPI

# URL 분석 라우터 가져오기
from app.routers.url_analysis import router


# 1. FastAPI 앱 생성
app = FastAPI(title="QR Guard URL Analysis API")


# 2. URL 분석 및 매장 검색 API 등록
app.include_router(router)
