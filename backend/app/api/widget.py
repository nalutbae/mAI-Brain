"""mAI-Brain — 임베디드 채팅 위젯 API

엔드포인트:
- GET    /api/widgets                     — 위젯 설정 목록
- POST   /api/widgets                     — 위젯 설정 생성
- GET    /api/widgets/{id}                — 위젯 설정 조회
- PUT    /api/widgets/{id}                — 위젯 설정 수정
- DELETE /api/widgets/{id}                 — 위젯 설정 삭제
- POST   /api/widgets/token               — 익명 토큰 발급
- GET    /api/widgets/{id}/snippet         — 삽입 스니펫 조회
- GET    /api/widgets/{id}/embed            — iframe 임베드 HTML 페이지
- GET    /api/widgets/{id}/embed.js         — JS 부트스트래핑 스크립트
"""

import hashlib
import hmac
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.widget_store import get_widget_store
from app.models.widget import (
    WidgetConfig,
    WidgetConfigCreate,
    WidgetConfigUpdate,
    WidgetConfigListResponse,
    WidgetTokenRequest,
    WidgetTokenResponse,
    WidgetSnippetResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── 토큰 시크릿 (환경변수 또는 자동 생성) ────────────────────────────────

_WIDGET_SECRET = os.environ.get("WIDGET_SECRET", "mai-brain-widget-secret-change-me")
TOKEN_TTL_SECONDS = int(os.environ.get("WIDGET_TOKEN_TTL", "86400"))


def _generate_token(widget_id: str) -> tuple[str, str]:
    """HMAC 기반 익명 토큰 생성.

    Returns:
        (token, expires_at_iso)
    """
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    msg = f"{widget_id}:{expires_at}"
    sig = hmac.new(
        _WIDGET_SECRET.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()
    token = f"{msg}:{sig}"
    expires_at_iso = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
    return token, expires_at_iso


def _verify_token(token: str, widget_id: str) -> bool:
    """토큰 검증."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return False
        token_widget_id, expires_str, sig = parts
        if token_widget_id != widget_id:
            return False
        expires_at = int(expires_str)
        if expires_at < int(time.time()):
            return False
        msg = f"{widget_id}:{expires_str}"
        expected_sig = hmac.new(
            _WIDGET_SECRET.encode(),
            msg.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except (ValueError, IndexError):
        return False


# ── 위젯 설정 CRUD ─────────────────────────────────────────────────────────

@router.get("", response_model=WidgetConfigListResponse)
def list_widgets():
    """위젯 설정 목록 조회."""
    store = get_widget_store()
    widgets = store.list_widgets()
    return WidgetConfigListResponse(widgets=widgets, total=len(widgets))


@router.post("", response_model=WidgetConfig, status_code=201)
def create_widget(data: WidgetConfigCreate):
    """위젯 설정 생성."""
    store = get_widget_store()
    return store.create_widget(data)


@router.get("/{widget_id}", response_model=WidgetConfig)
def get_widget_config(widget_id: str):
    """위젯 설정 조회."""
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return widget


@router.put("/{widget_id}", response_model=WidgetConfig)
def update_widget(widget_id: str, data: WidgetConfigUpdate):
    """위젯 설정 수정."""
    store = get_widget_store()
    widget = store.update_widget(widget_id, data)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return widget


@router.delete("/{widget_id}")
def delete_widget(widget_id: str):
    """위젯 설정 삭제."""
    store = get_widget_store()
    if not store.delete_widget(widget_id):
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")
    return {"message": "위젯이 삭제되었습니다", "widget_id": widget_id}


# ── 익명 토큰 발급 ─────────────────────────────────────────────────────────

@router.post("/token", response_model=WidgetTokenResponse)
def issue_token(request: WidgetTokenRequest):
    """위젯 익명 접근 토큰 발급.

    CORS 검증: 요청 origin이 위젯의 allowed_origins에 포함되어야 함.
    토큰은 HMAC 서명 기반이며, 만료 시간 포함.
    """
    store = get_widget_store()

    # 위젯 존재 확인
    widget = store.get_widget(request.widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    # 비활성 위젯
    if not widget.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 위젯입니다")

    # CORS 오리진 검증
    if not store.validate_origin(request.widget_id, request.origin):
        raise HTTPException(
            status_code=403,
            detail=f"오리진 '{request.origin}'은(는) 허용되지 않습니다",
        )

    # 토큰 생성
    token, expires_at = _generate_token(request.widget_id)

    return WidgetTokenResponse(
        token=token,
        widget_id=request.widget_id,
        expires_at=expires_at,
        config=widget,
    )


# ── 삽입 스니펫 ─────────────────────────────────────────────────────────────

@router.get("/{widget_id}/snippet", response_model=WidgetSnippetResponse)
def get_snippet(widget_id: str, request: Request):
    """위젯 삽입용 <script> 태그 스니펫 반환."""
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    base_url = str(request.base_url).rstrip("/")

    snippet = (
        f'<script\n'
        f'  src="{base_url}/api/widgets/{widget_id}/embed.js"\n'
        f'  data-widget-id="{widget_id}"\n'
        f'></script>'
    )

    iframe_url = f"{base_url}/api/widgets/{widget_id}/embed"

    return WidgetSnippetResponse(
        widget_id=widget_id,
        snippet=snippet,
        iframe_url=iframe_url,
    )


# ── iframe 임베드 HTML ─────────────────────────────────────────────────────

@router.get("/{widget_id}/embed", response_class=HTMLResponse)
def get_embed_page(widget_id: str, request: Request):
    """iframe 임베드용 최소 HTML 페이지.

    쿼리 파라미터:
    - token: 익명 접근 토큰 (필수)
    """
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    if not widget.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 위젯입니다")

    base_url = str(request.base_url).rstrip("/")
    theme = widget.theme
    workspace_id_val = widget.workspace_id or ""

    logo_html = f'<img class="logo" src="{widget.logo_url}" alt="logo">' if widget.logo_url else ""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{widget.name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: {theme.font_family}; background: {theme.background_color}; color: {theme.text_color}; }}
  .chat-container {{ display: flex; flex-direction: column; height: 100vh; }}
  .chat-header {{
    background: {theme.primary_color}; color: white; padding: 12px 16px;
    display: flex; align-items: center; gap: 8px; flex-shrink: 0;
  }}
  .chat-header img.logo {{ width: 28px; height: 28px; border-radius: 50%; }}
  .chat-header h1 {{ font-size: 14px; font-weight: 600; }}
  .chat-messages {{
    flex: 1; overflow-y: auto; padding: 16px;
    display: flex; flex-direction: column; gap: 8px;
  }}
  .greeting {{ text-align: center; color: {theme.text_color}99; padding: 32px 16px; font-size: 14px; }}
  .message {{
    max-width: 80%; padding: 10px 14px; border-radius: {theme.border_radius};
    font-size: 14px; line-height: 1.5; word-break: break-word;
  }}
  .message.user {{
    align-self: flex-end; background: {theme.user_bubble_color};
    color: {theme.user_bubble_text_color}; border-bottom-right-radius: 4px;
  }}
  .message.assistant {{
    align-self: flex-start; background: {theme.assistant_bubble_color};
    color: {theme.assistant_bubble_text_color}; border-bottom-left-radius: 4px;
  }}
  .message.error {{ align-self: center; background: #FEE2E2; color: #DC2626; font-size: 13px; }}
  .message .sources {{ font-size: 12px; color: {theme.text_color}88; margin-top: 4px; }}
  .chat-input-area {{
    padding: 12px; border-top: 1px solid {theme.primary_color}22;
    display: flex; gap: 8px; flex-shrink: 0; background: {theme.background_color};
  }}
  .chat-input {{
    flex: 1; padding: 10px 14px; border: 1px solid {theme.primary_color}44;
    border-radius: {theme.border_radius}; font-family: {theme.font_family};
    font-size: 14px; outline: none; resize: none;
    background: {theme.background_color}; color: {theme.text_color};
  }}
  .chat-input:focus {{ border-color: {theme.primary_color}; box-shadow: 0 0 0 2px {theme.primary_color}33; }}
  .chat-send {{
    padding: 10px 20px; background: {theme.primary_color}; color: white; border: none;
    border-radius: {theme.border_radius}; font-family: {theme.font_family};
    font-size: 14px; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
  }}
  .chat-send:hover {{ opacity: 0.9; }}
  .chat-send:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  .typing-dots {{ display: inline-flex; gap: 4px; padding: 4px 0; }}
  .typing-dots span {{
    width: 6px; height: 6px; background: {theme.primary_color}; border-radius: 50%;
    animation: bounce 1.4s infinite ease-in-out both;
  }}
  .typing-dots span:nth-child(1) {{ animation-delay: -0.32s; }}
  .typing-dots span:nth-child(2) {{ animation-delay: -0.16s; }}
  @keyframes bounce {{
    0%, 80%, 100% {{ transform: scale(0); }} 40% {{ transform: scale(1); }}
  }}
</style>
</head>
<body>
<div class="chat-container">
  <div class="chat-header">
    {logo_html}
    <h1>{widget.name}</h1>
  </div>
  <div class="chat-messages" id="messages">
    <div class="greeting">{widget.greeting}</div>
  </div>
  <div class="chat-input-area">
    <input type="text" class="chat-input" id="chatInput"
           placeholder="{widget.placeholder}" autocomplete="off" />
    <button class="chat-send" id="sendBtn">전송</button>
  </div>
</div>
<script>
(function() {{
  var API_BASE = '{base_url}';
  var WIDGET_ID = '{widget_id}';
  var WORKSPACE_ID = '{workspace_id_val}';
  var TOKEN_KEY = 'mai_brain_token_' + WIDGET_ID;
  var SESSION_KEY = 'mai_brain_session_' + WIDGET_ID;

  var sessionId = localStorage.getItem(SESSION_KEY) || null;
  var isLoading = false;

  var messagesEl = document.getElementById('messages');
  var inputEl = document.getElementById('chatInput');
  var sendBtn = document.getElementById('sendBtn');

  function getTokenFromUrl() {{
    var params = new URLSearchParams(window.location.search);
    return params.get('token');
  }}

  function getStoredToken() {{
    return localStorage.getItem(TOKEN_KEY);
  }}

  function storeToken(token) {{
    localStorage.setItem(TOKEN_KEY, token);
  }}

  function getToken() {{
    var urlToken = getTokenFromUrl();
    if (urlToken) {{
      storeToken(urlToken);
      return urlToken;
    }}
    return getStoredToken();
  }}

  function addMessage(role, content, sources) {{
    var greeting = messagesEl.querySelector('.greeting');
    if (greeting) greeting.remove();

    var div = document.createElement('div');
    div.className = 'message ' + role;
    div.textContent = content;

    if (sources && sources.length > 0) {{
      var srcDiv = document.createElement('div');
      srcDiv.className = 'sources';
      srcDiv.textContent = '\\uCD9C\\uCC98: ' + sources.map(function(s) {{ return s.source; }}).join(', ');
      div.appendChild(srcDiv);
    }}

    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }}

  function addTyping() {{
    var div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'typing-msg';
    div.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }}

  function removeTyping() {{
    var el = document.getElementById('typing-msg');
    if (el) el.remove();
  }}

  function sendMessage() {{
    var question = inputEl.value.trim();
    if (!question || isLoading) return;

    addMessage('user', question, null);
    inputEl.value = '';
    isLoading = true;
    sendBtn.disabled = true;
    addTyping();

    var token = getToken();
    var headers = {{ 'Content-Type': 'application/json' }};
    if (token) headers['Authorization'] = 'Bearer ' + token;

    var body = JSON.stringify({{
      question: question,
      mode: 'fact',
      session_id: sessionId,
      workspace_id: WORKSPACE_ID || undefined
    }});

    fetch(API_BASE + '/api/chat', {{
      method: 'POST', headers: headers, body: body
    }})
    .then(function(resp) {{
      if (!resp.ok) throw new Error('API error: ' + resp.status);
      return resp.json();
    }})
    .then(function(data) {{
      removeTyping();
      addMessage('assistant', data.answer, data.sources);
      if (data.session_id && !sessionId) {{
        sessionId = data.session_id;
        localStorage.setItem(SESSION_KEY, sessionId);
      }}
    }})
    .catch(function(err) {{
      removeTyping();
      addMessage('error', '\\uC624\\uB958: ' + err.message);
    }})
    .finally(function() {{
      isLoading = false;
      sendBtn.disabled = false;
      inputEl.focus();
    }});
  }}

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' && !e.shiftKey) {{
      e.preventDefault();
      sendMessage();
    }}
  }});

  getToken();
}})();
</script>
</body>
</html>"""

    return html


# ── JS 스니펫 제공 (script src) ────────────────────────────────────────────

@router.get("/{widget_id}/embed.js", response_class=HTMLResponse)
def get_embed_js(widget_id: str, request: Request):
    """<script> 태그로 삽입하는 위젯 부트스트래핑 JS.

    외부 웹사이트에서 <script src=".../embed.js">로 로드하면
    플로팅 버튼 + iframe 기반 채팅 위젯을 자동으로 생성한다.
    """
    store = get_widget_store()
    widget = store.get_widget(widget_id)
    if not widget:
        raise HTTPException(status_code=404, detail="위젯을 찾을 수 없습니다")

    base_url = str(request.base_url).rstrip("/")

    js = f"""(function() {{
  var WIDGET_ID = '{widget_id}';
  var BASE_URL = '{base_url}';
  var POSITION = '{widget.position}';
  var ORIGIN = window.location.origin;
  var WIDGET_NAME = '{widget.name}';
  var PRIMARY_COLOR = '{widget.theme.primary_color}';
  var BTN_SIZE = 56;
  var IFRAME_W = 380;
  var IFRAME_H = 560;

  var btnStyle = 'position:fixed;' +
    (POSITION === 'bottom-left' ? 'left:20px;' : 'right:20px;') +
    'bottom:20px;width:' + BTN_SIZE + 'px;height:' + BTN_SIZE + 'px;border-radius:50%;' +
    'background:' + PRIMARY_COLOR + ';' +
    'border:none;cursor:pointer;z-index:9999;' +
    'box-shadow:0 4px 12px rgba(0,0,0,0.15);display:flex;' +
    'align-items:center;justify-content:center;transition:transform 0.2s;';

  var chatIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
  var closeIcon = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';

  var btn = document.createElement('button');
  btn.setAttribute('style', btnStyle);
  btn.innerHTML = chatIcon;
  btn.title = WIDGET_NAME;
  document.body.appendChild(btn);

  var iframeContainer = null;
  var isOpen = false;

  function openWidget() {{
    if (iframeContainer) {{
      iframeContainer.style.display = 'block';
      isOpen = true;
      btn.innerHTML = closeIcon;
      return;
    }}

    fetch(BASE_URL + '/api/widgets/token', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ widget_id: WIDGET_ID, origin: ORIGIN }})
    }})
    .then(function(r) {{ return r.json(); }})
    .then(function(data) {{
      var token = data.token;
      var embedUrl = BASE_URL + '/api/widgets/' + WIDGET_ID + '/embed?token=' + encodeURIComponent(token);

      iframeContainer = document.createElement('div');
      iframeContainer.setAttribute('style',
        'position:fixed;' +
        (POSITION === 'bottom-left' ? 'left:20px;' : 'right:20px;') +
        'bottom:86px;width:' + IFRAME_W + 'px;height:' + IFRAME_H + 'px;' +
        'border-radius:12px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,0.2);' +
        'z-index:9998;'
      );

      var iframe = document.createElement('iframe');
      iframe.src = embedUrl;
      iframe.setAttribute('style', 'width:100%;height:100%;border:none;');
      iframe.setAttribute('allow', 'microphone;camera');
      iframeContainer.appendChild(iframe);
      document.body.appendChild(iframeContainer);

      isOpen = true;
      btn.innerHTML = closeIcon;
    }})
    .catch(function(err) {{
      console.error('mAI-Brain widget token error:', err);
    }});
  }}

  function closeWidget() {{
    if (iframeContainer) {{
      iframeContainer.style.display = 'none';
    }}
    isOpen = false;
    btn.innerHTML = chatIcon;
  }}

  btn.addEventListener('click', function() {{
    if (isOpen) closeWidget();
    else openWidget();
  }});

  btn.addEventListener('mouseenter', function() {{ btn.style.transform = 'scale(1.1)'; }});
  btn.addEventListener('mouseleave', function() {{ btn.style.transform = 'scale(1)'; }});
}})();
"""

    return HTMLResponse(content=js, media_type="application/javascript")