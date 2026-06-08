# mAI-Brain

**도메인 특화 RAG 챗봇 프레임워크** — 어떤 업무든 문서와 설정만으로 나만의 AI 챗봇을 구축할 수 있습니다.

## 아키텍처

```
사용자 질문 → 벡터DB 검색(Qdrant) → LLM 응답(DeepSeek/OpenAI/Ollama)
                                    ↑
                              문서 → 벡터 임베딩 → 저장
```

## 기술 스택

| 구성요소 | 기술 |
|----------|------|
| 프론트엔드 | Next.js 16 (정적) + nginx |
| 백엔드 | FastAPI + Python 3.11+ |
| 벡터DB | Qdrant |
| 임베딩 | OpenAI API / Ollama 로컬 / bge-m3 |
| LLM | DeepSeek API / ollama-cloud / any OpenAI-compatible |
| 배포 | Docker Compose |

## 기능

- **4가지 채팅 모드**: 팩트 조회, 요약, 컬럼 작성, 추론
- **추론 강도 선택**: 강한/중간/약한 근거 필터링
- **세션 기반 대화**: 이전 대화 컨텍스트 유지
- **멀티모달 문서**: PDF, EPUB, TXT 지원 (OCR 포함)
- **문서 관리**: 웹 UI에서 업로드/삭제/상태 확인

## 빠른 시작

```bash
# 1. 환경변수 설정
cp .env.example .env
# .env 파일 수정 (API 키 등)

# 2. 문서 업로드
# data/uploads/ 디렉토리에 PDF/EPUB/TXT 파일 복사

# 3. 실행
docker compose up -d --build

# 4. 접속
open http://localhost:3001
```

## 설정

`.env` 파일에서 다음을 설정하세요:

```env
# 임베딩 프로바이더: api (OpenAI), ollama (로컬), local (bge-m3)
EMBEDDING_PROVIDER=api
OPENAI_API_KEY=sk-...

# LLM 프로바이더: deepseek, ollama-cloud
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# 앱 이름 (UI에 표시)
APP_NAME=mAI-Brain
```

## 라이선스

MIT License — 자유롭게 사용, 수정, 배포하세요.
