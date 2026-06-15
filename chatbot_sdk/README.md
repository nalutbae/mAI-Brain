# mAI-Brain Service Chatbot SDK

웹사이트에 서비스 챗봇을 임베드하는 독립 실행형 JavaScript SDK입니다. 채널톡 스타일의 플로팅 아이콘과 팝업 채팅창을 제공합니다.

---

## 📋 목차

- [개요](#개요)
- [스크린샷](#스크린샷)
- [빠른 시작](#빠른-시작)
- [설치 방법](#설치-방법)
- [초기화 옵션](#초기화-옵션)
- [API 메서드](#api-메서드)
- [설정 파일 (JSON)](#설정-파일-json)
  - [branding](#branding)
  - [greeting](#greeting)
  - [faq](#faq)
  - [quick_replies](#quick_replies)
  - [workspace](#workspace)
  - [system_prompt](#system_prompt)
  - [disclaimer](#disclaimer)
- [관리자 설정 (설정 페이지)](#관리자-설정-설정-페이지)
- [백엔드 API 엔드포인트](#백엔드-api-엔드포인트)
- [커스터마이징](#커스터마이징)
- [트러블슈팅](#트러블슈팅)

---

## 개요

mAI-Brain 서비스 챗봇 SDK는 외부 웹사이트(회사 홈페이지, 안내 데스크, 고객센터 등)에 AI 기반 상담 챗봇을 쉽게 임베드할 수 있게 해줍니다.

**핵심 특징:**

- 🟢 **플로팅 아이콘** — 웹페이지 우측 하단에 항상 표시되는 채팅 버튼
- 💬 **슬라이드업 팝업** — 채널톡 스타일의 깔끔한 채팅 인터페이스
- ⚡ **실시간 스트리밍** — SSE 기반 토큰 단위 응답 렌더링
- 📋 **FAQ 카드** — 설정 파일로 관리되는 자주 묻는 질문
- 🔘 **객관식 선택지** — `question`(LLM 답변) / `answer`(고정 답변) 두 가지 타입
- 🎨 **동적 브랜딩** — JSON 설정 파일로 색상, 이름, 이모지, 프롬프트 완전 제어
- 📱 **반응형** — 모바일/데스크톱 자동 대응
- 🔒 **의존성 없음** — React, Vue 등 프레임워크 의존성 없이 순수 JavaScript

---

## 스크린샷

```
┌─────────────────────────────────┐
│  🤖 AI 서비스 어시스턴트    ─ × │  ← 그라디언트 헤더
│     무엇이든 물어보세요          │
├─────────────────────────────────┤
│                                 │
│  🤖 안녕하세요! 👋 저는       │
│     **AI 서비스 어시스턴트**   │  ← 인사 메시지
│     입니다. 궁금한 점이        │
│     있으시면 자유롭게...       │
│                                 │
│  🤖 ┌─────────────────────┐     │
│     │ 📋 이용 안내        │     │  ← FAQ 카드 그리드
│     │ 💰 요금 안내        │     │
│     │ ⏰ 운영시간         │     │
│     │ 📞 연락처           │     │
│     └─────────────────────┘     │
│                                 │
│  [요금 안내]  [이용 안내]       │  ← 객관식 선택지
│  [상담원 연결] [배송 조회]      │
│                                 │
├─────────────────────────────────┤
│  💬 질문을 입력하세요...    ➤  │  ← 입력 영역
├─────────────────────────────────┤
│      AI가 생성한 응답입니다     │  ← 면책 조항
└─────────────────────────────────┘
                                       🤖  ← 플로팅 아이콘
```

---

## 빠른 시작

가장 간단한 설치 — HTML에 한 줄 추가:

```html
<script src="https://your-server.com/sdk/maibot-sdk.js"
        data-api-base="https://your-server.com"></script>
```

페이지 로드 시 자동으로 플로팅 아이콘이 표시되고, 클릭하면 채팅창이 열립니다.

---

## 설치 방법

### 방법 1: `<script>` 태그 (권장)

```html
<!-- </body> 태그 앞에 추가 -->
<script src="/sdk/maibot-sdk.js"
        data-api-base="https://your-api-server.com"></script>
```

`data-api-base` 속성으로 백엔드 API 서버 URL을 지정합니다. 동일 출처(nginx 프록시)인 경우 생략 가능합니다.

```html
<!-- 동일 출처 (nginx가 /api/*를 백엔드로 프록시) -->
<script src="/sdk/maibot-sdk.js" data-api-base=""></script>
```

### 방법 2: 수동 초기화

설치 옵션을 커스터마이징하려면 수동 초기화를 사용합니다.

```html
<script src="/sdk/maibot-sdk.js"></script>
<script>
  MaibotSDK.init({
    apiBase: 'https://your-api-server.com',
    primaryColor: '#6366f1',  // 메인 컬러
    position: 'left',          // 플로팅 아이콘 위치
    offsetBottom: 32,          // 하단 여백 (px)
    offsetSide: 32,            // 측면 여백 (px)
  });
</script>
```

### 방법 3: npm 패키지 (향후 지원 예정)

```bash
npm install @mai-brain/chatbot-sdk
```

---

## 초기화 옵션

| 옵션 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `apiBase` | `string` | `""` | 백엔드 API 베이스 URL. 빈 문자열이면 동일 출처로 요청 |
| `primaryColor` | `string` | `"#2563eb"` | 메인 컬러. JSON 설정의 `branding.primary_color`가 우선 적용됨 |
| `position` | `"right"` \| `"left"` | `"right"` | 플로팅 아이콘 위치 |
| `offsetBottom` | `number` | `24` | 화면 하단에서의 여백 (px) |
| `offsetSide` | `number` | `24` | 화면 측면에서의 여백 (px) |
| `zIndex` | `number` | `999999` | CSS z-index 값 |

> **참고**: `primaryColor`는 초기화 옵션보다 JSON 설정 파일의 `branding.primary_color`가 우선 적용됩니다.

---

## API 메서드

### `MaibotSDK.init(options)`

SDK를 초기화하고 챗봇 UI를 렌더링합니다.

```javascript
await MaibotSDK.init({ apiBase: 'https://api.example.com' });
```

**반환값**: `Promise<MaibotSDK>` — 초기화 완료 후 SDK 객체를 반환합니다.

### `MaibotSDK.open()`

채팅 팝업을 엽니다.

```javascript
MaibotSDK.open();
```

### `MaibotSDK.close()`

채팅 팝업을 닫습니다.

```javascript
MaibotSDK.close();
```

### `MaibotSDK.toggle()`

채팅 팝업을 열거나 닫습니다.

```javascript
MaibotSDK.toggle();
```

### `MaibotSDK.destroy()`

SDK 인스턴스를 완전히 제거합니다. DOM 요소와 스타일시트를 포함합니다.

```javascript
MaibotSDK.destroy();
```

---

## 설정 파일 (JSON)

챗봇의 모든 텍스트, 브랜딩, FAQ, 객관식, RAG 프롬프트는 `backend/data/service_chat_config.json` 파일로 관리합니다. 코드 수정 없이 JSON 파일만 편집하면 됩니다.

```json
{
  "meta": {
    "version": 1,
    "updated_at": "2026-06-15T00:00:00Z",
    "description": "서비스 챗봇 설정 파일"
  },

  "branding": { ... },
  "greeting": { ... },
  "faq": { ... },
  "quick_replies": { ... },
  "system_prompt": { ... },
  "disclaimer": "..."
}
```

### `branding`

챗봇의 외관을 정의합니다.

```json
{
  "branding": {
    "bot_name": "AI 서비스 어시스턴트",
    "bot_emoji": "🤖",
    "header_title": "서비스 챗봇",
    "header_subtitle": "무엇이든 물어보세요 · AI 기반 실시간 상담",
    "primary_color": "#2563eb",
    "placeholder_text": "질문을 입력하세요..."
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `bot_name` | `string` | 봇 이름. `{{bot_name}}` 변수로 다른 필드에서 참조 가능 |
| `bot_emoji` | `string` | 플로팅 아이콘과 채팅 아바타에 표시할 이모지 |
| `header_title` | `string` | 팝업 헤더에 표시할 제목 |
| `header_subtitle` | `string` | 헤더 제목 아래 부제목 |
| `primary_color` | `string` | 메인 컬러 (CSS hex). FAB, 헤더 그라디언트, 선택지 호버에 적용 |
| `placeholder_text` | `string` | 채팅 입력창 플레이스홀더 |

### `greeting`

초기 인사 메시지를 정의합니다.

```json
{
  "greeting": {
    "message": "안녕하세요! 👋 저는 **{{bot_name}}**입니다.\n\n궁금한 점이 있으시면 자유롭게 질문해 주세요.",
    "show_on_new_chat": true
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `message` | `string` | 인사 메시지. 마크다운 지원. `{{bot_name}}` 변수 치환 가능 |
| `show_on_new_chat` | `boolean` | 새 대화 시작 시 인사 메시지 표시 여부 |

> `{{bot_name}}`은 `branding.bot_name` 값으로 자동 치환됩니다.

### `faq`

채팅창 초기 화면에 표시되는 자주 묻는 질문 카드입니다.

```json
{
  "faq": {
    "section_title": "자주 묻는 질문",
    "items": [
      {
        "id": "faq-usage",
        "icon": "📋",
        "label": "이용 안내",
        "question": "서비스 이용 방법을 알려주세요"
      },
      {
        "id": "faq-pricing",
        "icon": "💰",
        "label": "요금 안내",
        "question": "요금 체계가 어떻게 되나요?"
      },
      {
        "id": "faq-hours",
        "icon": "⏰",
        "label": "운영시간",
        "question": "운영시간이 어떻게 되나요?"
      },
      {
        "id": "faq-contact",
        "icon": "📞",
        "label": "연락처",
        "question": "고객센터 연락처를 알려주세요"
      }
    ]
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `section_title` | `string` | FAQ 섹션 제목 (현재 미사용, 향후 확장용) |
| `items[].id` | `string` | 고유 식별자 |
| `items[].icon` | `string` | 카드에 표시할 이모지 |
| `items[].label` | `string` | 카드에 표시할 짧은 라벨 |
| `items[].question` | `string` | 카드 클릭 시 LLM에 전송할 질문 문장 |

> 카드 클릭 시 `question` 필드가 자동으로 채팅 입력으로 전송됩니다.

### `quick_replies`

객관식 선택지 버튼을 정의합니다. 두 가지 트리거 시점과 두 가지 응답 타입이 있습니다.

```json
{
  "quick_replies": {
    "groups": [
      {
        "trigger": "first_message",
        "title": "무엇을 도와드릴까요?",
        "options": [
          {
            "id": "qr-pricing",
            "type": "question",
            "label": "요금 안내",
            "value": "요금 체계에 대해 알려주세요"
          },
          {
            "id": "qr-hours",
            "type": "question",
            "label": "운영시간",
            "value": "운영시간이 어떻게 되나요?"
          },
          {
            "id": "qr-human",
            "type": "answer",
            "label": "상담원 연결",
            "answer": "📞 고객센터: 02-1234-5678\n📧 이메일: support@example.com\n⏰ 운영시간: 평일 09:00~18:00\n\n상담원 연결을 원하시면 전화로 문의해 주세요."
          }
        ]
      },
      {
        "trigger": "after_answer",
        "title": "추가로 궁금한 점이 있으신가요?",
        "options": [
          {
            "id": "qr-more",
            "type": "question",
            "label": "더 질문하기",
            "value": ""
          },
          {
            "id": "qr-new",
            "type": "question",
            "label": "새 대화 시작",
            "value": ""
          }
        ]
      }
    ]
  }
}
```

#### 트리거 타입

| `trigger` 값 | 표시 시점 |
|---------------|-----------|
| `"first_message"` | 인사 메시지 직후 (최초 진입 시) |
| `"after_answer"` | AI 답변 완료 후 |
| `"always"` | 항상 표시 (위 두 시점 모두) |

#### 선택지 타입

| `type` 값 | 동작 |
|-----------|------|
| `"question"` | `value`(또는 `label`)를 LLM에 질문으로 전송 |
| `"answer"` | `answer` 필드의 고정 텍스트를 봇 메시지로 즉시 표시 |

> `value`가 빈 문자열이면 `label` 텍스트가 질문으로 전송됩니다.

### `workspace`

서비스 챗봇이 RAG 검색을 수행할 **워크스페이스**를 지정합니다.

```json
{
  "workspace": "전체"
}
```

| 값 | 설명 |
|---|------|
| `"전체"` (기본값) | 모든 워크스페이스의 문서를 검색합니다 |
| 워크스페이스 ID | 해당 워크스페이스에 할당된 문서만 검색합니다 |

> **동작 원리**: `"전체"` 또는 빈 문자열이면 백엔드에서 `workspace_id=None`으로 처리되어 전체 컬렉션을 검색합니다. 특정 워크스페이스 ID가 지정되면 해당 컬렉션만 검색합니다.
>
> **관리자 설정에서 변경**: 설정 페이지(⚙️ 설정 → 🤖 서비스 챗봇)의 **검색 워크스페이스** 드롭다운에서 워크스페이스를 선택할 수 있습니다.

### `system_prompt`

LLM의 응답 방향과 성격을 제어하는 RAG 시스템 프롬프트입니다.

```json
{
  "system_prompt": {
    "base": "당신은 {{bot_name}}입니다. 다음 지침을 엄격히 따르세요:\n\n1. 항상 정중하고 친절한 한국어 존댓말(~해요, ~습니다)을 사용하세요.\n2. 제공된 문서 내용만 근거로 답변하세요.\n3. 문서에 없는 내용은 \"해당 정보를 찾을 수 없습니다\"라고 솔직히 말하세요.\n4. 추측이나 임의의 정보를 만들지 마세요.\n5. 출처 인용 마커([[N]])는 사용하지 마세요.\n6. \"제공된 문서에 따르면\" 같은 표현은 피하세요.\n7. 고객이 이해하기 쉬운 평이한 언어로 설명하세요.\n8. 관련 정보가 부족하면 고객센터 연락처를 안내하세요.",
    "mode_instructions": {
      "fact": "[서비스 상담 모드 — 팩트 조회]\n- 정확한 사실 위주로 간결하게 답변하세요.\n- 핵심 정보를 먼저 제시하고 필요 시 부연 설명을 덧붙이세요.\n- 확실하지 않은 정보는 제공하지 마세요.",
      "summary": "[서비스 상담 모드 — 요약]\n- 핵심 포인트를 3~5개의 항목으로 요약하세요.\n- 고객이 빠르게 파악할 수 있도록 구조화하세요.",
      "reasoning": "[서비스 상담 모드 — 추론]\n- 논리적 단계별로 분석하여 답변하세요.\n- 결론을 먼저 제시하고 근거를 설명하세요."
    },
    "user_prompt_template": "[검색 결과]\n{context}\n\n[고객 질문]\n{query}\n\n위 검색 결과를 바탕으로 고객 질문에 답변하세요."
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `base` | `string` | 기본 시스템 프롬프트. `{{bot_name}}` 변수 치환 가능 |
| `mode_instructions` | `object` | 채팅 모드별 추가 지시문 (`fact`, `summary`, `reasoning`) |
| `user_prompt_template` | `string` | RAG 사용자 프롬프트 템플릿. `{context}`와 `{query}` 변수 포함 |

> 서비스 챗봇은 항상 `fact` 모드로 고정 실행됩니다.

### `disclaimer`

채팅 입력창 하단에 표시되는 면책 조항입니다.

```json
{
  "disclaimer": "AI가 생성한 응답이므로 정확하지 않을 수 있습니다. 중요한 사항은 공식 채널로 확인해 주세요."
}
```

---

## 관리자 설정 (설정 페이지)

관리자는 웹 UI의 **⚙️ 설정 → 🤖 서비스 챗봇** 메뉴에서 다음 항목을 제어할 수 있습니다.

### 검색 워크스페이스

| 설정 | 설명 |
|------|------|
| **전체** (기본값) | 모든 워크스페이스의 문서를 검색합니다 |
| 특정 워크스페이스 | 해당 워크스페이스에 할당된 문서만 검색합니다 |

- 드롭다운에 등록된 워크스페이스 목록이 자동으로 표시됩니다
- 저장하면 `service_chat_config.json`의 `workspace` 필드가 업데이트됩니다
- 챗봇이 새 대화를 시작할 때 이 설정값을 `workspace_id`로 백엔드에 전달합니다

### 출처 및 인용 표시

| 설정 | 설명 |
|------|------|
| **표시 모드** (ON) | 출처와 인용 정보가 답변과 함께 표시됩니다. 전문적인 상담용 |
| **친근 모드** (OFF) | 출처와 인용 없이 자연스럽고 친근한 문체로 답변합니다. 일반 고객 응대용 |

### 상세 설정 (JSON 직접 편집)

브랜딩, 인사말, FAQ, 객관식, 시스템 프롬프트 등은 `backend/data/service_chat_config.json` 파일을 직접 편집하거나 API로 업데이트합니다.

```bash
# 전체 설정 조회
curl http://localhost:8000/api/service-chat/config

# 전체 설정 업데이트 (workspace 변경 예시)
curl -X PUT http://localhost:8000/api/service-chat/config \
  -H "Content-Type: application/json" \
  -d '{"workspace": "8ca62c21"}'

# 설정 리로드 (JSON 파일 수정 후)
curl -X POST http://localhost:8000/api/service-chat/config/reload
```

> **주의**: JSON 파일을 직접 수정한 후에는 반드시 **리로드 API**를 호출하거나 서버를 재시작해야 변경사항이 반영됩니다.

---

## 백엔드 API 엔드포인트

SDK는 다음 백엔드 API를 사용합니다.

| Method | URL | 설명 |
|--------|-----|------|
| `GET` | `/api/service-chat/config` | 챗봇 설정 로드 (브랜딩, 인사, FAQ, 객관식, 프롬프트) |
| `POST` | `/api/chat/stream` | SSE 스트리밍 채팅 (`service_mode: true` 자동 설정) |
| `PUT` | `/api/service-chat/config` | 설정 부분 업데이트 (운영자용) |
| `POST` | `/api/service-chat/config/reload` | JSON 파일 직접 편집 후 리로드 |

### SSE 이벤트 형식

```
event: token
data: {"content": "안녕하"}

event: token
data: {"content": "세요"}

event: done
data: {"session_id": "abc123"}
```

---

## 커스터마이징

### JSON 파일 직접 편집

`backend/data/service_chat_config.json` 파일을 편집한 후 리로드 API를 호출합니다.

```bash
# 설정 편집
vim backend/data/service_chat_config.json

# 서버에 리로드 요청
curl -X POST http://localhost:8000/api/service-chat/config/reload
```

### API를 통한 부분 업데이트

```bash
# 봇 이름만 변경
curl -X PUT http://localhost:8000/api/service-chat/config \
  -H "Content-Type: application/json" \
  -d '{"branding": {"bot_name": "금융 상담봇", "bot_emoji": "💰"}}'

# 인사 메시지만 변경
curl -X PUT http://localhost:8000/api/service-chat/config \
  -H "Content-Type: application/json" \
  -d '{"greeting": {"message": "안녕하세요! 금융 상담봇입니다.", "show_on_new_chat": true}}'
```

### CSS 오버라이드

SDK 스타일을 덮어쓰려면 `!important`를 사용합니다.

```css
/* FAB 크기 변경 */
.maibot-fab { width: 64px !important; height: 64px !important; }

/* 팝업 너비 변경 */
.maibot-popup { width: 420px !important; }

/* 봇 말풍긴 색상 변경 */
.maibot-bubble-bot { background: #f0fdf4 !important; }
```

---

## 트러블슈팅

### 플로팅 아이콘이 보이지 않는 경우

1. **백엔드 서버가 실행 중인지 확인** — SDK가 `/api/service-chat/config`를 호출해야 합니다.
2. **CORS 설정 확인** — 백엔드 `config.py`의 `cors_origins`에 프론트엔드 오리진이 포함되어야 합니다.
3. **브라우저 콘솔 확인** — `[MaibotSDK]` 접두사의 로그를 확인합니다.

### 채팅 응답이 오지 않는 경우

1. **`/api/chat/stream` 응답 상태 확인** — 401/403이면 인증 문제입니다.
2. **`service_mode: true` 확인** — SDK가 자동으로 `service_mode: true`를 전송합니다.
3. **백엔드 LLM 프로바이더 상태 확인** — 활성 LLM 프로바이더가 설정되어 있어야 합니다.

### 설정이 반영되지 않는 경우

1. **JSON 문법 오류 확인** — 유효하지 않은 JSON이면 설정 로드가 실패합니다.
2. **리로드 API 호출** — 파일 편집 후 `POST /api/service-chat/config/reload`를 호출하세요.
3. **브라우저 캐시 초기화** — 설정은 SDK 초기화 시 한 번 로드됩니다. 페이지 새로고침하세요.

### CORS 에러가 발생하는 경우

```
Access to fetch at 'http://localhost:8000/api/service-chat/config' from origin
'http://localhost:3001' has been blocked by CORS policy
```

→ 백엔드 `config.py`의 `cors_origins`에 프론트엔드 오리진을 추가합니다.

```python
cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
```

---

## 파일 구조

```
chatbot_sdk/
  maibot-sdk.js          ← 독립 실행형 SDK (프레임워크 의존성 없음)

frontend/public/sdk/
  maibot-sdk.js          ← 정적 서빙용 복사본 (/sdk/maibot-sdk.js)

backend/data/
  service_chat_config.json  ← 챗봇 설정 파일 (운영자 편집)
```