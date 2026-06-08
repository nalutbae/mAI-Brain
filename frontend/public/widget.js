/**
 * mAI-Brain 임베디드 채팅 위젯 — JS 스니펫
 *
 * 사용법:
 *   <script src="https://yourdomain.com/widget.js"
 *           data-widget-url="https://yourdomain.com/widget"
 *           data-primary-color="#2563eb"
 *           data-position="bottom-right"></script>
 *
 * 커스터마이징 (data-* 속성):
 *   - data-widget-url: 위젯 페이지 URL (필수)
 *   - data-primary-color: 주 색상 (기본값: #2563eb)
 *   - data-position: 위치 (기본값: bottom-right)
 *       가능: bottom-right, bottom-left, top-right, top-left
 *   - data-greeting: 초기 인사말 (기본값: "무엇을 도와드릴까요?")
 *   - data-width: 채팅창 너비 (기본값: 380px)
 *   - data-height: 채팅창 높이 (기본값: 600px)
 */

(function () {
  "use strict";

  // 이미 로드된 경우 중복 실행 방지
  if (document.getElementById("mai-brain-widget-container")) return;

  const script = document.currentScript;
  if (!script) return;

  // 설정 읽기
  const widgetUrl = script.getAttribute("data-widget-url") || "/widget";
  const primaryColor = script.getAttribute("data-primary-color") || "#2563eb";
  const position = script.getAttribute("data-position") || "bottom-right";
  const greeting = script.getAttribute("data-greeting") || "무엇을 도와드릴까요?";
  const width = script.getAttribute("data-width") || "380px";
  const height = script.getAttribute("data-height") || "600px";

  // 위치별 CSS
  const positionStyles = {
    "bottom-right": { bottom: "20px", right: "20px" },
    "bottom-left": { bottom: "20px", left: "20px" },
    "top-right": { top: "20px", right: "20px" },
    "top-left": { top: "20px", left: "20px" },
  };
  const pos = positionStyles[position] || positionStyles["bottom-right"];

  // z-index (가장 높은 값 + 1)
  const zIndex = 2147483647;

  // ── 스타일 주입 ──────────────────────────────────────────────────────

  const style = document.createElement("style");
  style.textContent = `
    #mai-brain-widget-container {
      position: fixed;
      ${Object.entries(pos)
        .map(([k, v]) => `${k}: ${v};`)
        .join("\n        ")}
      z-index: ${zIndex};
      font-family: system-ui, -apple-system, sans-serif;
      line-height: 1.5;
    }

    #mai-brain-widget-bubble {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: ${primaryColor};
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 16px rgba(0,0,0,0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.2s, box-shadow 0.2s;
      color: white;
      position: relative;
    }

    #mai-brain-widget-bubble:hover {
      transform: scale(1.08);
      box-shadow: 0 6px 24px rgba(0,0,0,0.2);
    }

    #mai-brain-widget-bubble svg {
      width: 26px;
      height: 26px;
    }

    #mai-brain-widget-bubble.mai-brain-hidden {
      display: none;
    }

    #mai-brain-widget-frame-wrapper {
      display: none;
      position: fixed;
      bottom: 80px;
      width: ${width};
      max-width: calc(100vw - 40px);
      height: ${height};
      max-height: calc(100vh - 120px);
      border-radius: 16px;
      overflow: hidden;
      box-shadow: 0 8px 32px rgba(0,0,0,0.15);
      background: white;
      transition: opacity 0.25s, transform 0.25s;
      opacity: 0;
      transform: translateY(10px);
    }

    #mai-brain-widget-frame-wrapper.mai-brain-open {
      display: block;
      opacity: 1;
      transform: translateY(0);
    }

    #mai-brain-widget-frame {
      width: 100%;
      height: 100%;
      border: none;
    }

    #mai-brain-widget-close {
      position: absolute;
      top: 8px;
      right: 8px;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba(0,0,0,0.4);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      z-index: ${zIndex + 2};
      transition: background 0.15s;
    }

    #mai-brain-widget-close:hover {
      background: rgba(0,0,0,0.6);
    }

    #mai-brain-widget-close svg {
      width: 14px;
      height: 14px;
    }
  `;
  document.head.appendChild(style);

  // ── DOM 생성 ─────────────────────────────────────────────────────────

  const container = document.createElement("div");
  container.id = "mai-brain-widget-container";

  // 채팅 버블 (항상 표시)
  const bubble = document.createElement("button");
  bubble.id = "mai-brain-widget-bubble";
  bubble.setAttribute("aria-label", "채팅 열기");
  bubble.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
  `;

  // 채팅 프레임 래퍼 (숨김 상태)
  const frameWrapper = document.createElement("div");
  frameWrapper.id = "mai-brain-widget-frame-wrapper";

  const closeButton = document.createElement("button");
  closeButton.id = "mai-brain-widget-close";
  closeButton.setAttribute("aria-label", "닫기");
  closeButton.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <line x1="18" y1="6" x2="6" y2="18"/>
      <line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  `;

  const frame = document.createElement("iframe");
  frame.id = "mai-brain-widget-frame";
  frame.src = widgetUrl;
  frame.setAttribute("title", "mAI-Brain 채팅");
  frame.setAttribute("allow", "clipboard-write");

  frameWrapper.appendChild(closeButton);
  frameWrapper.appendChild(frame);
  container.appendChild(bubble);
  container.appendChild(frameWrapper);
  document.body.appendChild(container);

  // ── 이벤트 핸들러 ────────────────────────────────────────────────────

  let isOpen = false;

  bubble.addEventListener("click", () => {
    isOpen = true;
    bubble.classList.add("mai-brain-hidden");
    frameWrapper.classList.add("mai-brain-open");
  });

  closeButton.addEventListener("click", () => {
    isOpen = false;
    frameWrapper.classList.remove("mai-brain-open");
    bubble.classList.remove("mai-brain-hidden");
  });

  // ESC 키로 닫기
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) {
      isOpen = false;
      frameWrapper.classList.remove("mai-brain-open");
      bubble.classList.remove("mai-brain-hidden");
    }
  });
})();
