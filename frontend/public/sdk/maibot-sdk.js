/**
 * mAI-Brain Service Chatbot SDK
 *
 * 채널톡 스타일 — 웹페이지 하단 플로팅 아이콘 + 클릭 시 팝업 채팅창
 *
 * 사용법:
 *   <script src="maibot-sdk.js" data-api-base="http://localhost:8000"></script>
 *   또는
 *   <script>
 *     MaibotSDK.init({ apiBase: 'http://localhost:8000' });
 *   </script>
 */
(function (global) {
  "use strict";

  // ── 기본 설정 ────────────────────────────────────────────────────────
  const DEFAULTS = {
    apiBase: "",
    primaryColor: "#2563eb",
    position: "right", // "right" | "left"
    offsetBottom: 24,
    offsetSide: 24,
    zIndex: 999999,
  };

  // ── 상태 ──────────────────────────────────────────────────────────────
  let config = null;
  let settings = { apiBase: "", ...DEFAULTS };
  let isOpen = false;
  let isMinimized = false;
  let messages = [];
  let sessionId = null;
  let isLoading = false;
  let activeQuickReplies = [];

  // DOM refs
  let container, fab, popup, chatBody, inputArea, inputEl;

  // ── 유틸 ──────────────────────────────────────────────────────────────
  function escapeHtml(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  /** 간단한 마크다운 → HTML (볼드, 이탤릭, 링크, 줄바꿈, 리스트) */
  function renderMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    // 볼드
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // 이탤릭
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    // 링크
    html = html.replace(
      /\[(.+?)\]\((.+?)\)/g,
      '<a href="$2" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline">$1</a>'
    );
    // 순서 없는 리스트
    html = html.replace(/^[-•]\s+(.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");
    // 번호 리스트
    html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
    // 줄바꿈
    html = html.replace(/\n\n/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");
    return "<p>" + html + "</p>";
  }

  /** {{변수}} 치환 */
  function renderTemplate(text, vars) {
    return text.replace(/\{\{(\w+)\}\}/g, (_, key) => vars[key] || _);
  }

  // ── API ────────────────────────────────────────────────────────────────
  async function fetchJSON(path) {
    const url = settings.apiBase + path;
    const resp = await fetch(url, {
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`);
    return resp.json();
  }

  async function loadConfig() {
    try {
      config = await fetchJSON("/api/service-chat/config");
    } catch (e) {
      console.warn("[MaibotSDK] 설정 로드 실패, 기본값 사용:", e);
      config = {
        branding: { bot_name: "AI 어시스턴트", bot_emoji: "🤖", header_title: "서비스 챗봇", header_subtitle: "", primary_color: "#2563eb", placeholder_text: "질문을 입력하세요..." },
        greeting: { message: "안녕하세요! 👋 궁금한 점이 있으시면 자유롭게 질문해 주세요.", show_on_new_chat: true },
        faq: { section_title: "자주 묻는 질문", items: [] },
        quick_replies: { groups: [] },
        disclaimer: "",
      };
    }
    applyConfig();
  }

  function applyConfig() {
    if (!config) return;
    const c = config.branding;
    // FAB 색상
    if (fab) fab.style.backgroundColor = c.primary_color || settings.primaryColor;
    // 팝업 헤더
    const header = popup?.querySelector(".maibot-header");
    if (header) {
      header.style.background = `linear-gradient(135deg, ${c.primary_color || settings.primaryColor}, ${adjustColor(c.primary_color || settings.primaryColor, -30)})`;
    }
    // 봇 이름
    const nameEl = popup?.querySelector(".maibot-bot-name");
    if (nameEl) nameEl.textContent = c.bot_name;
    const subtitleEl = popup?.querySelector(".maibot-subtitle");
    if (subtitleEl) subtitleEl.textContent = c.header_subtitle || "";
    // 플레이스홀더
    if (inputEl) inputEl.placeholder = c.placeholder_text || "질문을 입력하세요...";
    // 면책
    const disclaimer = popup?.querySelector(".maibot-disclaimer");
    if (disclaimer) disclaimer.textContent = config.disclaimer || "";
  }

  function adjustColor(hex, amount) {
    const num = parseInt(hex.replace("#", ""), 16);
    const r = Math.min(255, Math.max(0, (num >> 16) + amount));
    const g = Math.min(255, Math.max(0, ((num >> 8) & 0xff) + amount));
    const b = Math.min(255, Math.max(0, (num & 0xff) + amount));
    return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
  }

  // ── SSE 스트리밍 채팅 ────────────────────────────────────────────────
  async function sendMessage(text) {
    if (!text.trim() || isLoading) return;
    const question = text.trim();

    // 사용자 메시지 추가
    addMessage("user", question);
    isLoading = true;
    activeQuickReplies = [];
    renderMessages();
    hideQuickReplies();

    // AI 빈 메시지 (스트리밍용)
    const aiIdx = messages.length;
    addMessage("assistant", "");
    renderMessages();

    let fullAnswer = "";

    try {
      const body = JSON.stringify({
        question,
        mode: "fact",
        session_id: sessionId || undefined,
        service_mode: true,
      });

      const resp = await fetch(settings.apiBase + "/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body,
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data:")) {
            try {
              const payload = JSON.parse(line.slice(5).trim());
              if (payload.content) {
                fullAnswer += payload.content;
                messages[aiIdx].content = fullAnswer;
                renderMessages();
                scrollToBottom();
              }
              if (payload.session_id) {
                sessionId = payload.session_id;
              }
            } catch {}
          }
        }
      }

      // 스트리밍 완료 후 객관식 표시
      showPostAnswerQuickReplies();
    } catch (e) {
      console.error("[MaibotSDK] 스트리밍 오류:", e);
      // 폴백: 일반 API 호출
      try {
        const data = await fetchJSON("/api/chat");
        // 이건 POST여야 함 — 폴백은 간단하게 에러 메시지로
      } catch {
        messages[aiIdx].content = "죄송합니다. 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
        renderMessages();
      }
    } finally {
      isLoading = false;
    }
  }

  // ── 메시지 관리 ──────────────────────────────────────────────────────
  function addMessage(role, content, extra) {
    messages.push({ role, content, timestamp: new Date(), ...extra });
  }

  function showPostAnswerQuickReplies() {
    if (!config) return;
    const groups = config.quick_replies.groups.filter(
      (g) => g.trigger === "after_answer" || g.trigger === "always"
    );
    activeQuickReplies = groups;
    renderQuickReplies();
  }

  function showInitialQuickReplies() {
    if (!config) return;
    const groups = config.quick_replies.groups.filter(
      (g) => g.trigger === "first_message" || g.trigger === "always"
    );
    activeQuickReplies = groups;
    renderQuickReplies();
  }

  function handleQuickReply(option) {
    if (option.type === "answer" && option.answer) {
      addMessage("user", option.label);
      addMessage("assistant", option.answer);
      renderMessages();
      hideQuickReplies();
      showPostAnswerQuickReplies();
    } else {
      sendMessage(option.value || option.label);
    }
  }

  // ── DOM 렌더링 ──────────────────────────────────────────────────────
  function createUI() {
    // 컨테이너
    container = document.createElement("div");
    container.id = "maibot-sdk-root";
    container.style.cssText = `position:fixed;bottom:${settings.offsetBottom}px;${settings.position}:${settings.offsetSide}px;z-index:${settings.zIndex};font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;`;

    // FAB (Floating Action Button)
    fab = document.createElement("button");
    fab.className = "maibot-fab";
    fab.setAttribute("aria-label", "채팅 열기");
    fab.innerHTML = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`;
    fab.onclick = togglePopup;

    // 팝업
    popup = document.createElement("div");
    popup.className = "maibot-popup";
    popup.style.display = "none";
    popup.innerHTML = buildPopupHTML();

    container.appendChild(popup);
    container.appendChild(fab);
    document.body.appendChild(container);

    // 캐시 DOM refs
    chatBody = popup.querySelector(".maibot-body");
    inputArea = popup.querySelector(".maibot-input-area");
    inputEl = popup.querySelector(".maibot-input");

    // 이벤트 바인딩
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const text = inputEl.value.trim();
        if (text) {
          sendMessage(text);
          inputEl.value = "";
          inputEl.style.height = "auto";
        }
      }
    });

    popup.querySelector(".maibot-send-btn").addEventListener("click", () => {
      const text = inputEl.value.trim();
      if (text) {
        sendMessage(text);
        inputEl.value = "";
        inputEl.style.height = "auto";
      }
    });

    popup.querySelector(".maibot-close-btn").addEventListener("click", () => {
      closePopup();
    });

    popup.querySelector(".maibot-new-chat-btn").addEventListener("click", () => {
      resetChat();
    });

    // 자동 리사이즈
    inputEl.addEventListener("input", () => {
      inputEl.style.height = "auto";
      inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
    });

    applyConfig();
  }

  function buildPopupHTML() {
    return `
      <div class="maibot-header">
        <div class="maibot-header-left">
          <div class="maibot-avatar">🤖</div>
          <div>
            <div class="maibot-bot-name">서비스 챗봇</div>
            <div class="maibot-subtitle"></div>
          </div>
        </div>
        <div class="maibot-header-right">
          <button class="maibot-new-chat-btn" title="새 대화">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          <button class="maibot-close-btn" title="닫기">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
      <div class="maibot-body"></div>
      <div class="maibot-quick-replies"></div>
      <div class="maibot-input-area">
        <textarea class="maibot-input" placeholder="질문을 입력하세요..." rows="1"></textarea>
        <button class="maibot-send-btn" title="전송">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
        </button>
      </div>
      <div class="maibot-disclaimer"></div>
    `;
  }

  function renderMessages() {
    if (!chatBody) return;
    let html = "";
    for (const msg of messages) {
      if (msg.role === "user") {
        html += `<div class="maibot-msg-user"><div class="maibot-bubble maibot-bubble-user">${escapeHtml(msg.content)}</div></div>`;
      } else if (msg.role === "assistant") {
        // FAQ 카드 특별 렌더링
        if (msg.content === "__FAQ_CARDS__") {
          let faqHtml = "";
          if (config?.faq?.items?.length) {
            faqHtml += `<div class="maibot-faq-grid">`;
            for (const item of config.faq.items) {
              faqHtml += `<div class="maibot-faq-card" data-faq-id="${escapeHtml(item.id)}"><span class="maibot-faq-icon">${item.icon || "📋"}</span><span>${escapeHtml(item.label)}</span></div>`;
            }
            faqHtml += `</div>`;
          }
          html += `
            <div class="maibot-msg-bot">
              <div class="maibot-bot-avatar-small">${config?.branding?.bot_emoji || "🤖"}</div>
              <div class="maibot-bubble maibot-bubble-bot">${faqHtml}</div>
            </div>`;
        } else {
          const content = msg.content
            ? renderMarkdown(msg.content)
            : `<div class="maibot-typing"><span></span><span></span><span></span></div>`;
          html += `
            <div class="maibot-msg-bot">
              <div class="maibot-bot-avatar-small">${config?.branding?.bot_emoji || "🤖"}</div>
              <div class="maibot-bubble maibot-bubble-bot">${content}</div>
            </div>`;
        }
      }
    }
    chatBody.innerHTML = html;
    // FAQ 카드 클릭 이벤트 바인딩
    chatBody.querySelectorAll(".maibot-faq-card").forEach((card) => {
      card.addEventListener("click", () => {
        const faqId = card.dataset.faqId;
        const item = config?.faq?.items?.find((i) => i.id === faqId);
        if (item) {
          sendMessage(item.question);
        }
      });
    });
    scrollToBottom();
  }

  function renderQuickReplies() {
    const container = popup?.querySelector(".maibot-quick-replies");
    if (!container) return;

    if (activeQuickReplies.length === 0) {
      container.innerHTML = "";
      container.style.display = "none";
      return;
    }

    container.style.display = "block";
    let html = "";
    for (const group of activeQuickReplies) {
      if (group.title) {
        html += `<div class="maibot-qr-title">${escapeHtml(group.title)}</div>`;
      }
      html += `<div class="maibot-qr-options">`;
      for (const opt of group.options) {
        html += `<button class="maibot-qr-btn" data-qr-id="${escapeHtml(opt.id)}">${escapeHtml(opt.label)}</button>`;
      }
      html += `</div>`;
    }
    container.innerHTML = html;

    // 이벤트 바인딩
    container.querySelectorAll(".maibot-qr-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const qrId = btn.dataset.qrId;
        const opt = findQuickReplyOption(qrId);
        if (opt) handleQuickReply(opt);
      });
    });
  }

  function hideQuickReplies() {
    activeQuickReplies = [];
    renderQuickReplies();
  }

  function findQuickReplyOption(id) {
    if (!config) return null;
    for (const group of config.quick_replies.groups) {
      for (const opt of group.options) {
        if (opt.id === id) return opt;
      }
    }
    return null;
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
    });
  }

  // ── 팝업 제어 ─────────────────────────────────────────────────────────
  function togglePopup() {
    if (isOpen) closePopup();
    else openPopup();
  }

  function openPopup() {
    if (!popup) return;
    isOpen = true;
    popup.style.display = "flex";
    popup.style.animation = "maibot-slide-up 0.3s ease-out";
    fab.innerHTML = `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    fab.setAttribute("aria-label", "채팅 닫기");
    if (inputEl) inputEl.focus();
  }

  function closePopup() {
    if (!popup) return;
    isOpen = false;
    popup.style.animation = "maibot-slide-down 0.2s ease-in";
    setTimeout(() => {
      popup.style.display = "none";
    }, 180);
    const emoji = config?.branding?.bot_emoji || "🤖";
    fab.innerHTML = `<span style="font-size:24px;line-height:1">${emoji}</span>`;
    fab.setAttribute("aria-label", "채팅 열기");
  }

  function resetChat() {
    messages = [];
    sessionId = null;
    if (config?.greeting?.show_on_new_chat) {
      addMessage("assistant", renderTemplate(config.greeting.message, { bot_name: config.branding.bot_name }));
    }
    // FAQ 카드 렌더링 (초기 화면)
    if (config?.faq?.items?.length) {
      let faqHtml = "";
      for (const item of config.faq.items) {
        faqHtml += `<div class="maibot-faq-card" data-faq-id="${escapeHtml(item.id)}"><span class="maibot-faq-icon">${item.icon || "📋"}</span><span>${escapeHtml(item.label)}</span></div>`;
      }
      // FAQ는 마지막 봇 메시지에 추가하거나 별도 메시지로
      addMessage("assistant", "__FAQ_CARDS__");
    }
    renderMessages();
    showInitialQuickReplies();
  }

  // ── 스타일 주입 ──────────────────────────────────────────────────────
  function injectStyles() {
    if (document.getElementById("maibot-sdk-styles")) return;
    const style = document.createElement("style");
    style.id = "maibot-sdk-styles";
    style.textContent = `
/* ── FAB ───────────────────────────────────────────────────── */
.maibot-fab {
  width: 56px; height: 56px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 14px rgba(0,0,0,0.25);
  transition: transform 0.2s, box-shadow 0.2s;
  z-index: 999999;
  position: relative;
}
.maibot-fab:hover { transform: scale(1.08); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }
.maibot-fab:active { transform: scale(0.95); }

/* ── Popup ─────────────────────────────────────────────────── */
.maibot-popup {
  display: none;
  flex-direction: column;
  position: absolute;
  bottom: 68px;
  width: 380px;
  max-width: calc(100vw - 48px);
  height: 560px;
  max-height: calc(100vh - 100px);
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 12px 40px rgba(0,0,0,0.2);
  background: #fff;
  flex-shrink: 0;
}

/* ── Header ───────────────────────────────────────────────── */
.maibot-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #fff;
  flex-shrink: 0;
}
.maibot-header-left {
  display: flex; align-items: center; gap: 10px;
}
.maibot-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
}
.maibot-bot-name { font-weight: 600; font-size: 15px; line-height: 1.2; }
.maibot-subtitle { font-size: 12px; opacity: 0.85; }
.maibot-header-right {
  display: flex; gap: 4px;
}
.maibot-new-chat-btn, .maibot-close-btn {
  background: rgba(255,255,255,0.15);
  border: none;
  color: #fff;
  width: 32px; height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.15s;
}
.maibot-new-chat-btn:hover, .maibot-close-btn:hover {
  background: rgba(255,255,255,0.3);
}

/* ── Body (Messages) ──────────────────────────────────────── */
.maibot-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f8fafc;
}
.maibot-msg-user {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}
.maibot-msg-bot {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}
.maibot-bot-avatar-small {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.maibot-bubble {
  max-width: 85%;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}
.maibot-bubble-user {
  background: #2563eb;
  color: #fff;
  border-radius: 18px 18px 4px 18px;
}
.maibot-bubble-bot {
  background: #fff;
  color: #1e293b;
  border-radius: 18px 18px 18px 4px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.maibot-bubble-bot p { margin: 0 0 8px 0; }
.maibot-bubble-bot p:last-child { margin-bottom: 0; }
.maibot-bubble-bot ul, .maibot-bubble-bot ol { padding-left: 20px; margin: 4px 0; }
.maibot-bubble-bot li { margin: 2px 0; }
.maibot-bubble-bot strong { font-weight: 600; }
.maibot-bubble-bot a { color: #2563eb; }

/* ── Typing Indicator ──────────────────────────────────────── */
.maibot-typing {
  display: flex; gap: 4px; padding: 4px 0;
}
.maibot-typing span {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  animation: maibot-bounce 1.4s infinite;
}
.maibot-typing span:nth-child(2) { animation-delay: 0.2s; }
.maibot-typing span:nth-child(3) { animation-delay: 0.4s; }

/* ── Quick Replies ────────────────────────────────────────── */
.maibot-quick-replies {
  padding: 0 12px 8px 12px;
  max-height: 120px;
  overflow-y: auto;
  background: #f8fafc;
  flex-shrink: 0;
}
.maibot-qr-title {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 6px;
  font-weight: 500;
}
.maibot-qr-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.maibot-qr-btn {
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.maibot-qr-btn:hover {
  background: #eff6ff;
  border-color: #2563eb;
  color: #2563eb;
}

/* ── Input Area ───────────────────────────────────────────── */
.maibot-input-area {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border-top: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.maibot-input {
  flex: 1;
  border: 1px solid #e2e8f0;
  border-radius: 20px;
  padding: 10px 16px;
  font-size: 14px;
  resize: none;
  outline: none;
  font-family: inherit;
  line-height: 1.4;
  max-height: 100px;
  background: #f8fafc;
  transition: border-color 0.15s;
}
.maibot-input:focus {
  border-color: #2563eb;
  background: #fff;
}
.maibot-send-btn {
  width: 40px; height: 40px;
  border-radius: 50%;
  border: none;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: background 0.15s, transform 0.1s;
}
.maibot-send-btn:hover { background: #1d4ed8; }
.maibot-send-btn:active { transform: scale(0.92); }
.maibot-send-btn:disabled { background: #94a3b8; cursor: not-allowed; }

/* ── Disclaimer ───────────────────────────────────────────── */
.maibot-disclaimer {
  text-align: center;
  font-size: 11px;
  color: #94a3b8;
  padding: 4px 16px 10px;
  background: #fff;
  flex-shrink: 0;
}

/* ── Animations ───────────────────────────────────────────── */
@keyframes maibot-slide-up {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes maibot-slide-down {
  from { opacity: 1; transform: translateY(0); }
  to { opacity: 0; transform: translateY(20px); }
}
@keyframes maibot-bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* ── FAQ Cards (초기 표시) ───────────────────────────────── */
.maibot-faq-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}
.maibot-faq-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 13px;
  color: #334155;
}
.maibot-faq-card:hover {
  background: #eff6ff;
  border-color: #2563eb;
}
.maibot-faq-icon { font-size: 18px; }
    `;
    document.head.appendChild(style);
  }

  // ── 공개 API ──────────────────────────────────────────────────────────
  const SDK = {
    init: async function (options) {
      settings = { ...DEFAULTS, ...options };

      injectStyles();
      createUI();
      await loadConfig();

      // 인사 메시지
      resetChat();

      return SDK;
    },
    open: openPopup,
    close: closePopup,
    toggle: togglePopup,
    destroy: function () {
      container?.remove();
      document.getElementById("maibot-sdk-styles")?.remove();
    },
  };

  // ── 자동 초기화 ──────────────────────────────────────────────────────
  // 1) data-api-base 속성으로 자동 초기화 (직접 <script> 태그 삽입 시)
  // 2) 그 외에는 MaibotSDK.init() 수동 호출 필요
  function autoInit() {
    // data-api-base가 있는 <script> 태그에서 로드된 경우
    const scripts = document.querySelectorAll('script[data-api-base]');
    const currentSrc = document.currentScript?.src || '';
    let apiBase = '';
    
    // 현재 스크립트 태그의 data-api-base 우선
    if (document.currentScript && document.currentScript.dataset.apiBase) {
      apiBase = document.currentScript.dataset.apiBase;
    } else if (scripts.length > 0) {
      // 가장 최근 스크립트 태그 사용
      apiBase = scripts[scripts.length - 1].dataset.apiBase || '';
    }
    
    if (apiBase !== undefined) {  // 빈 문자열도 허용 (동일 출장)
      SDK.init({ apiBase });
    }
  }

  // DOM 준비 후 자동 초기화 시도
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoInit);
  } else {
    // 이미 DOM이 준비됨 — 약간의 지연으로 외부 스크립트 속성 읽기 보장
    setTimeout(autoInit, 0);
  }

  global.MaibotSDK = SDK;
})(typeof window !== "undefined" ? window : this);