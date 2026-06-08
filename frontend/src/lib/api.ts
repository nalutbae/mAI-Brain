/**
 * 백엔드 API 클라이언트
 * FastAPI 백엔드와 통신합니다.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchAPI<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// ── 헬스체크 ──────────────────────────────────────────────────────────────
export async function healthCheck(): Promise<{ status: string; app: string }> {
  return fetchAPI("/health");
}

// ── 채팅 메시지 ───────────────────────────────────────────────────────────

export type ChatMode = "fact" | "summary" | "column" | "reasoning";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Array<{ source: string; text: string; score: number; page?: number }>;
}

export type ReasoningStrength = "all" | "strong" | "mid" | "weak";

export interface ChatRequest {
  question: string;
  mode: ChatMode;
  session_id?: string;
  reasoning_strength?: ReasoningStrength;
}

export interface ChatResponse {
  answer: string;
  sources?: Array<{ source: string; text: string; score: number; page?: number }>;
  session_id: string;
}

export async function chatApi(request: ChatRequest): Promise<ChatResponse> {
  return fetchAPI<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ── 문서 관리 ─────────────────────────────────────────────────────────────

export interface Document {
  document_id: string;
  filename: string;
  status: "pending" | "indexing" | "completed" | "failed";
  total_chunks?: number;
  created_at?: string;
}

export async function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * 여러 파일을 한 번에 업로드 (배치)
 */
export async function uploadMultipleDocuments(files: File[]): Promise<Document[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(`${API_BASE_URL}/api/documents/upload-multiple`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export async function getDocuments(): Promise<Document[]> {
  const response = await fetch(`${API_BASE_URL}/api/documents`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  return data.documents || [];
}

export async function deleteDocument(id: string): Promise<{ message: string; document_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/documents/${id}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// ── 세션 관리 ─────────────────────────────────────────────────────────────

export interface Session {
  id: string;
  session_id: string;
  title: string;
  created_at: string;
}

export async function getSessions(): Promise<Session[]> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  // Backend returns {sessions: [...], total: N} — extract, map session_id→id
  return (data.sessions || []).map((s: any) => ({
    ...s,
    id: s.session_id,
  }));
}

export async function createSession(title: string): Promise<Session> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  // Backend returns {session_id, title, ...}
  return { ...data, id: data.session_id };
}

export async function getSession(id: string): Promise<{ session: Session; messages: ChatMessage[] }> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${id}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  return {
    ...data,
    session: { ...data, id: data.session_id },
  };
}