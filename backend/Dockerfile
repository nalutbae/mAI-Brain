# 범용 AI 챗봇 — 백엔드 Dockerfile
# 단일 스테이지: build-essential 설치 → uv sync → build-essential 제거
FROM python:3.11-slim

WORKDIR /app

# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 빌드 의존성 + OCR 의존성 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치 (캐시 최적화)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# 빌드 의존성 제거 (최종 이미지 크기 최적화)
RUN apt-get purge -y build-essential python3-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 앱 코드 복사
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
