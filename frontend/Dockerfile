# mAI-Brain AI 챗봇 — 프론트엔드 Dockerfile
# Next.js 정적 빌드 → nginx 서빙
FROM node:20-alpine AS builder

WORKDIR /app

# 의존성 설치 (캐시 최적화)
COPY package.json package-lock.json* ./
RUN npm ci

# 소스 코드 복사
COPY . .

# 환경변수 설정 (빌드 시)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# 정적 빌드
RUN npm run build

# ── 실행 스테이지 ─────────────────────────────────────────────────────────
FROM nginx:alpine

# nginx 설정
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 정적 파일 복사
COPY --from=builder /app/out /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]