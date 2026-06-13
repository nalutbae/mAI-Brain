/**
 * 백엔드 API 클라이언트
 * FastAPI 백엔드와 통신합니다.
 */

// nginx가 /api를 프록시하는 경우 빈 문자열(상대 경로) 사용.
// 직접 백엔드에 연결하는 경우 http://localhost:8000 등으로 설정.
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "";

export async function fetchAPI<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
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

export type ChatMode = "fact" | "summary" | "column" | "reasoning" | "creative";

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
  workspace_id?: string;
}

export interface ChatResponse {
  answer: string;
  sources?: Array<{ source: string; text: string; score: number; page?: number }>;
  citations?: Citation[];
  session_id: string;
}

export async function chatApi(request: ChatRequest): Promise<ChatResponse> {
  return fetchAPI<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ── 채팅 스트리밍 ────────────────────────────────────────────────────────

export interface Citation {
  index: number;
  source: string;
  page?: number;
  text: string;
  score: number;
}

export interface StreamCallbacks {
  /** 토큰 조각 수신 시 호출 */
  onToken: (token: string) => void;
  /** 검색 출처 수신 시 호출 */
  onSources?: (sources: Array<{ source: string; text: string; score: number; page?: number }>) => void;
  /** 인용 마커 수신 시 호출 ([[N]] → Citation 매핑) */
  onCitations?: (citations: Citation[]) => void;
  /** 에이전트 스텝 수신 시 호출 */
  onSteps?: (steps: Array<{ type: string; content: string; tool_name?: string }>) => void;
  /** 스트리밍 완료 시 호출 (session_id 포함) */
  onDone: (sessionId: string) => void;
  /** 오류 발생 시 호출 */
  onError: (error: string) => void;
}

/**
 * SSE 스트리밍 채팅 API.
 * fetch + ReadableStream을 사용하여 서버에서 토큰을 점진적으로 수신한다.
 * EventSource 대신 fetch를 사용하는 이유: POST 요청 지원 + 커스텀 헤더.
 */
export async function chatStreamApi(
  request: ChatRequest,
  callbacks: StreamCallbacks
): Promise<void> {
  const url = `${API_BASE_URL}/api/chat/stream`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
      },
      body: JSON.stringify(request),
    });
  } catch (err) {
    callbacks.onError(err instanceof Error ? err.message : "네트워크 오류가 발생했습니다.");
    return;
  }

  if (!response.ok) {
    callbacks.onError(`API 오류: ${response.status} ${response.statusText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError("응답 스트림을 읽을 수 없습니다.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE는 빈 줄(\n\n)로 이벤트를 구분
      const events = buffer.split("\n\n");
      // 마지막 조각은 완전하지 않을 수 있으므로 버퍼에 유지
      buffer = events.pop() || "";

      for (const eventStr of events) {
        if (!eventStr.trim()) continue;

        let eventType = "";
        let eventData = "";

        for (const line of eventStr.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6);
          }
        }

        if (!eventType || !eventData) continue;

        try {
          const data = JSON.parse(eventData);

          switch (eventType) {
            case "token":
              if (data.content) {
                callbacks.onToken(data.content);
              }
              break;
            case "sources":
              if (callbacks.onSources && data.sources) {
                callbacks.onSources(data.sources);
              }
              break;
            case "citations":
              if (callbacks.onCitations && data.citations) {
                callbacks.onCitations(data.citations);
              }
              break;
            case "steps":
              if (callbacks.onSteps && data.steps) {
                callbacks.onSteps(data.steps);
              }
              break;
            case "done":
              callbacks.onDone(data.session_id || request.session_id || "");
              break;
            case "error":
              callbacks.onError(data.error || "알 수 없는 오류가 발생했습니다.");
              break;
          }
        } catch {
          // JSON 파싱 실패 — 무시
        }
      }
    }
  } catch (err) {
    callbacks.onError(err instanceof Error ? err.message : "스트리밍 중 오류가 발생했습니다.");
  } finally {
    reader.releaseLock();
  }
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
 * URL 웹페이지를 다운로드하여 인덱싱
 */
export async function uploadUrl(url: string): Promise<Document> {
  return fetchAPI(`/api/documents/upload-url?url=${encodeURIComponent(url)}`, {
    method: "POST",
  });
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

// ── 문서 재인덱스 ──────────────────────────────────────────────────────────

export interface ReindexResult {
  reindexed: number;
  failed: number;
  details: Array<{ document_id: string; status: string }>;
}

export async function reindexAllDocuments(): Promise<ReindexResult> {
  return fetchAPI("/api/documents/reindex-all", { method: "POST" });
}

export async function reindexDocument(id: string): Promise<{ message: string; document_id: string }> {
  return fetchAPI(`/api/documents/${id}/reindex`, { method: "POST" });
}

export async function getDocumentDetail(id: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/api/documents/${id}`);
}

// ── 비동기 태스크 (업로드 + SSE 진행률) ──────────────────────────────────

export interface TaskStatus {
  id: string;
  status: "pending" | "processing" | "completed" | "failed";
  progress: number;  // 0-100
  result?: {
    document_id: string;
    filename: string;
    status: string;
    total_chunks?: number;
    error?: string | null;
  };
  error?: string | null;
  created_at?: string;
  completed_at?: string | null;
}

export interface UploadAsyncResult {
  task_id: string;
  document_id: string;
  filename: string;
  status: "pending";
  message: string;
}

/**
 * 비동기 파일 업로드 — 태스크 ID를 즉시 반환하고 인덱싱은 백그라운드에서 진행.
 * SSE로 진행률을 스트리밍할 수 있습니다.
 */
export async function uploadDocumentAsync(file: File): Promise<UploadAsyncResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/documents/upload-async`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * 여러 파일 비동기 업로드 — 각각 태스크 ID 반환
 */
export async function uploadMultipleDocumentsAsync(files: File[]): Promise<UploadAsyncResult[]> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  const response = await fetch(`${API_BASE_URL}/api/documents/upload-multiple-async`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

/**
 * 태스크 상태 폴링
 */
export async function getTaskStatus(taskId: string): Promise<TaskStatus> {
  return fetchAPI(`/api/documents/task/${taskId}`);
}

/** SSE 진행률 이벤트 타입 */
export interface TaskProgressEvent {
  type: "progress" | "completed" | "failed" | "done" | "heartbeat";
  progress?: number;
  message?: string;
  result?: TaskStatus["result"];
  error?: string;
}

export interface TaskStreamCallbacks {
  onProgress?: (progress: number, message?: string) => void;
  onCompleted?: (result: TaskStatus["result"]) => void;
  onFailed?: (error: string) => void;
  onDone?: () => void;
  onError?: (error: string) => void;
}

/**
 * SSE 스트리밍 — 태스크 진행률 실시간 수신.
 * fetch + ReadableStream을 사용 (EventSource 대신 POST/인증 지원).
 */
export async function streamTaskProgress(
  taskId: string,
  callbacks: TaskStreamCallbacks
): Promise<void> {
  const url = `${API_BASE_URL}/api/documents/task/${taskId}/stream`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      credentials: "include",
      headers: {
        Accept: "text/event-stream",
      },
    });
  } catch (err) {
    callbacks.onError?.(err instanceof Error ? err.message : "네트워크 오류가 발생했습니다.");
    return;
  }

  if (!response.ok) {
    callbacks.onError?.(`API 오류: ${response.status} ${response.statusText}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.("응답 스트림을 읽을 수 없습니다.");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE는 빈 줄(\n\n)로 이벤트를 구분
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventStr of events) {
        if (!eventStr.trim()) continue;

        let eventType = "";
        let eventData = "";

        for (const line of eventStr.split("\n")) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            eventData = line.slice(6);
          }
        }

        if (!eventType) continue;

        // done 이벤트는 데이터가 없을 수 있음
        if (eventType === "done") {
          callbacks.onDone?.();
          return;
        }

        if (eventType === "heartbeat") continue;

        let data: TaskProgressEvent;
        try {
          data = JSON.parse(eventData);
        } catch {
          continue;
        }

        switch (eventType) {
          case "progress":
            callbacks.onProgress?.(data.progress ?? 0, data.message);
            break;
          case "completed":
            callbacks.onCompleted?.(data.result);
            break;
          case "failed":
            callbacks.onFailed?.(data.error || "인덱싱에 실패했습니다.");
            break;
        }
      }
    }
  } catch (err) {
    callbacks.onError?.(err instanceof Error ? err.message : "스트리밍 중 오류가 발생했습니다.");
  } finally {
    reader.releaseLock();
  }
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

export async function deleteSession(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
}

// ── RAG 평가 ─────────────────────────────────────────────────────────────

export interface QAPair {
  id: string;
  question: string;
  expected_answer: string;
  expected_sources: string[];
  mode: string;
  tags: string[];
}

export interface QAPairCreate {
  question: string;
  expected_answer: string;
  expected_sources?: string[];
  mode?: string;
  tags?: string[];
}

export interface SingleEvalResult {
  qa_id: string;
  question: string;
  expected_answer: string;
  actual_answer: string;
  retrieved_sources: string[];
  expected_sources: string[];
  precision_at_k: number;
  recall_at_k: number;
  mrr: number;
  faithfulness: number;
  answer_relevance: number;
  hallucination_score: number;
}

export interface EvaluationRun {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  qa_pair_ids: string[];
  mode: string | null;
  results: SingleEvalResult[];
  created_at: string;
  completed_at: string | null;
  avg_precision: number;
  avg_recall: number;
  avg_mrr: number;
  avg_faithfulness: number;
  avg_answer_relevance: number;
  avg_hallucination_score: number;
}

export interface EvaluationStats {
  total_qa_pairs: number;
  total_evaluations: number;
  avg_precision: number;
  avg_recall: number;
  avg_mrr: number;
  avg_faithfulness: number;
  avg_answer_relevance: number;
  avg_hallucination_score: number;
  recent_evaluations: string[];
}

// QA Pairs
export async function listQAPairs(): Promise<QAPair[]> {
  return fetchAPI<QAPair[]>("/api/evaluation/qa-pairs");
}

export async function createQAPair(data: QAPairCreate): Promise<QAPair> {
  return fetchAPI<QAPair>("/api/evaluation/qa-pairs", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteQAPair(id: string): Promise<void> {
  await fetchAPI(`/api/evaluation/qa-pairs/${id}`, { method: "DELETE" });
}

export async function updateQAPair(
  id: string,
  data: { question?: string; expected_answer?: string; category?: string },
): Promise<QAPair> {
  return fetchAPI(`/api/evaluation/qa-pairs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function exportEvaluationResults(format: string = "json"): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/api/evaluation/results/export?format=${format}`,
    { headers: { "Content-Type": "application/json" } },
  );
  if (!response.ok) throw new Error(`Export failed: ${response.status}`);
  return response.blob();
}

// Evaluation
export async function runEvaluation(qaPairIds?: string[], mode?: string): Promise<EvaluationRun> {
  return fetchAPI<EvaluationRun>("/api/evaluation/run", {
    method: "POST",
    body: JSON.stringify({ qa_pair_ids: qaPairIds || [], mode }),
  });
}

export async function listEvaluationResults(): Promise<EvaluationRun[]> {
  return fetchAPI<EvaluationRun[]>("/api/evaluation/results");
}

export async function getEvaluationResult(id: string): Promise<EvaluationRun> {
  return fetchAPI<EvaluationRun>(`/api/evaluation/results/${id}`);
}

export async function getEvaluationStats(): Promise<EvaluationStats> {
  return fetchAPI<EvaluationStats>("/api/evaluation/stats");
}

// ── 청킹 프로파일 ──────────────────────────────────────────────────────

export type ChunkingStrategy = "fixed" | "sentence" | "paragraph" | "section" | "article";

export interface ChunkingProfile {
  id: string;
  name: string;
  description: string;
  strategy: ChunkingStrategy;
  chunk_size: number;
  chunk_overlap: number;
  separator_pattern: string;
  min_chunk_size: number;
  metadata_fields: string[];
  is_default: boolean;
  created_at: string;
}

export interface ChunkingProfileCreate {
  name: string;
  description?: string;
  strategy?: ChunkingStrategy;
  chunk_size?: number;
  chunk_overlap?: number;
  separator_pattern?: string;
  min_chunk_size?: number;
  metadata_fields?: string[];
}

export interface ChunkingProfileUpdate {
  name?: string;
  description?: string;
  strategy?: ChunkingStrategy;
  chunk_size?: number;
  chunk_overlap?: number;
  separator_pattern?: string;
  min_chunk_size?: number;
  metadata_fields?: string[];
}

export interface ChunkPreviewItem {
  index: number;
  text: string;
  full_length: number;
  metadata: Record<string, unknown>;
}

export interface ChunkPreview {
  profile_id: string;
  total_chunks: number;
  chunks: ChunkPreviewItem[];
  avg_chunk_size: number;
  total_chars: number;
}

export interface ChunkPreviewRequest {
  text: string;
  profile_id?: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

// 청킹 프로파일 API
export async function listChunkingProfiles(): Promise<ChunkingProfile[]> {
  return fetchAPI<ChunkingProfile[]>("/api/chunking/profiles");
}

export async function createChunkingProfile(data: ChunkingProfileCreate): Promise<ChunkingProfile> {
  return fetchAPI<ChunkingProfile>("/api/chunking/profiles", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateChunkingProfile(
  id: string,
  data: ChunkingProfileUpdate
): Promise<ChunkingProfile> {
  return fetchAPI<ChunkingProfile>(`/api/chunking/profiles/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteChunkingProfile(id: string): Promise<void> {
  await fetchAPI(`/api/chunking/profiles/${id}`, { method: "DELETE" });
}

export async function setDefaultChunkingProfile(
  id: string
): Promise<ChunkingProfile> {
  return fetchAPI<ChunkingProfile>(`/api/chunking/profiles/${id}/default`, {
    method: "POST",
  });
}

export async function previewChunking(
  request: ChunkPreviewRequest
): Promise<ChunkPreview> {
  return fetchAPI<ChunkPreview>("/api/chunking/preview", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ── 피드백 (Human-in-the-Loop RAG) ─────────────────────────────────────────

export type FeedbackType = "thumbs_up" | "thumbs_down" | "correction";
export type FeedbackTag =
  | "irrelevant"
  | "incomplete"
  | "outdated"
  | "hallucination"
  | "wrong_source"
  | "biased"
  | "unclear";
export type CorrectionType = "retrieval" | "answer";
export type ImprovementTarget =
  | "top_k"
  | "chunk_size"
  | "embedding_model"
  | "prompt"
  | "reindex";

export interface Feedback {
  id: string;
  session_id: string;
  query: string;
  answer: string;
  feedback_type: FeedbackType;
  tags: FeedbackTag[];
  comment: string;
  correction_type: CorrectionType | null;
  correction_text: string;
  created_at: string;
}

export interface FeedbackCreate {
  session_id?: string;
  message_index?: number;
  query?: string;
  answer?: string;
  feedback_type: FeedbackType;
  tags?: FeedbackTag[];
  comment?: string;
  correction_type?: CorrectionType;
  correction_text?: string;
}

export interface FeedbackStats {
  total_feedbacks: number;
  thumbs_up: number;
  thumbs_down: number;
  corrections: number;
  satisfaction_rate: number;
  tag_distribution: Record<string, number>;
  recent_trend: { thumbs_up: number; thumbs_down: number };
}

export interface FeedbackSuggestion {
  id: string;
  target: ImprovementTarget;
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  affected_feedback_ids: string[];
  data: Record<string, unknown>;
  is_applied: boolean;
  created_at: string;
}

export async function submitFeedback(data: FeedbackCreate): Promise<Feedback> {
  return fetchAPI<Feedback>("/api/feedback", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listFeedback(params?: {
  feedback_type?: FeedbackType;
  session_id?: string;
  limit?: number;
}): Promise<Feedback[]> {
  const searchParams = new URLSearchParams();
  if (params?.feedback_type) searchParams.set("feedback_type", params.feedback_type);
  if (params?.session_id) searchParams.set("session_id", params.session_id);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  const qs = searchParams.toString();
  return fetchAPI<Feedback[]>(`/api/feedback${qs ? `?${qs}` : ""}`);
}

export async function getFeedbackStats(): Promise<FeedbackStats> {
  return fetchAPI<FeedbackStats>("/api/feedback/stats");
}

export async function getFeedbackSuggestions(): Promise<FeedbackSuggestion[]> {
  return fetchAPI<FeedbackSuggestion[]>("/api/feedback/suggestions");
}

export async function getSessionFeedback(sessionId: string): Promise<Feedback[]> {
  return fetchAPI<Feedback[]>(`/api/feedback/session/${sessionId}`);
}

// ── 프로바이더 설정 ──────────────────────────────────────────────────────

export type LLMProvider = "ollama" | "openai" | "anthropic" | "groq" | "deepseek" | "custom";
export type EmbeddingProvider = "local" | "openai" | "jina" | "ollama" | "cohere";

export interface APIKeyStatus {
  is_set: boolean;
  masked: string;
}

export interface LLMProviderConfig {
  id: string;
  provider: LLMProvider;
  name: string;
  api_key_env_var: string;
  api_key_status: APIKeyStatus;
  base_url: string;
  model: string;
  is_active: boolean;
  temperature: number;
  max_tokens: number;
  fallback_provider_id: string;
  created_at: string;
  updated_at: string;
  effective_base_url: string;
  effective_model: string;
  display_name: string;
}

export interface EmbeddingConfig {
  provider: EmbeddingProvider;
  api_key_env_var: string;
  api_key_status: APIKeyStatus;
  base_url: string;
  model: string;
  dim: number;
}

export interface ProviderDefaults {
  provider: string;
  default_base_url: string;
  default_model: string;
  supports_streaming: boolean;
  supports_tools: boolean;
  requires_api_key: boolean;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  model_info?: string;
  response_time_ms?: number;
}

// LLM 프로바이더 CRUD
export async function listLLMProviders(): Promise<{ providers: LLMProviderConfig[]; active_id: string | null }> {
  return fetchAPI("/api/settings/providers/llm");
}

export async function createLLMProvider(data: {
  id?: string;
  provider: LLMProvider;
  name?: string;
  api_key_env_var?: string;
  base_url?: string;
  model?: string;
  is_active?: boolean;
  temperature?: number;
  max_tokens?: number;
  fallback_provider_id?: string;
}): Promise<LLMProviderConfig> {
  return fetchAPI("/api/settings/providers/llm", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateLLMProvider(
  id: string,
  data: Partial<Omit<LLMProviderConfig, "id" | "created_at" | "updated_at" | "effective_base_url" | "effective_model" | "display_name">>
): Promise<LLMProviderConfig> {
  return fetchAPI(`/api/settings/providers/llm/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteLLMProvider(id: string): Promise<{ message: string }> {
  return fetchAPI(`/api/settings/providers/llm/${id}`, { method: "DELETE" });
}

export async function activateLLMProvider(id: string): Promise<LLMProviderConfig> {
  return fetchAPI(`/api/settings/providers/llm/${id}/activate`, { method: "POST" });
}

// 임베딩 프로바이더
export async function getEmbeddingProvider(): Promise<EmbeddingConfig> {
  return fetchAPI("/api/settings/providers/embedding");
}

export async function updateEmbeddingProvider(data: {
  provider: EmbeddingProvider;
  api_key_env_var?: string;
  base_url?: string;
  model?: string;
  dim?: number;
}): Promise<EmbeddingConfig> {
  return fetchAPI("/api/settings/providers/embedding", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// 사용 가능한 프로바이더 목록
export async function listAvailableLLMProviders(): Promise<{ providers: ProviderDefaults[] }> {
  return fetchAPI("/api/settings/providers/available/llm");
}

export async function listAvailableEmbeddingProviders(): Promise<{
  providers: Array<{
    provider: string;
    description: string;
    default_model: string;
    default_base_url: string;
    default_dim: number;
    requires_api_key: boolean;
  }>;
}> {
  return fetchAPI("/api/settings/providers/available/embedding");
}

// 연결 테스트
export async function testProviderConnection(data: {
  provider: LLMProvider;
  api_key_env_var?: string;
  base_url?: string;
  model?: string;
}): Promise<ConnectionTestResult> {
  return fetchAPI("/api/settings/providers/test", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// 전체 설정 조회
export async function getFullSettings(): Promise<{
  llm: { providers: LLMProviderConfig[]; active_id: string | null };
  embedding: EmbeddingConfig;
  reranker: RerankerConfig;
}> {
  return fetchAPI("/api/settings/settings");
}

// ── 리랭커 설정 ──────────────────────────────────────────────────────────

export interface RerankerConfig {
  enabled: boolean;
  model: string;
  min_score: number;
}

export async function getRerankerConfig(): Promise<RerankerConfig> {
  const settings = await fetchAPI<{ llm: unknown; embedding: unknown; reranker: RerankerConfig }>("/api/settings/settings");
  return settings.reranker;
}

export async function updateRerankerConfig(data: {
  enabled?: boolean;
  model?: string;
  min_score?: number;
}): Promise<RerankerConfig & { message: string }> {
  return fetchAPI("/api/settings/settings/reranker", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ── OCR 설정 ──────────────────────────────────────────────────────────────

export interface OcrConfig {
  provider: "surya" | "tesseract" | "none";
  languages: string[];
  dpi: number;
  max_pages: number;
  enable_table: boolean;
}

export async function getOcrConfig(): Promise<OcrConfig> {
  const settings = await fetchAPI<{ llm: unknown; embedding: unknown; reranker: unknown; ocr: OcrConfig }>("/api/settings/settings");
  return settings.ocr;
}

export async function updateOcrConfig(data: {
  provider?: string;
  languages?: string[];
  dpi?: number;
  max_pages?: number;
  enable_table?: boolean;
}): Promise<OcrConfig & { message: string }> {
  return fetchAPI("/api/settings/settings/ocr", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ── 세션 내보내기 ──────────────────────────────────────────────────────

export type ExportFormat = "markdown" | "json" | "csv";

/**
 * 단일 세션 대화 내보내기 (다운로드)
 */
export function exportSessionUrl(sessionId: string, format: ExportFormat = "markdown"): string {
  return `${API_BASE_URL}/api/sessions/${sessionId}/export?format=${format}`;
}

/**
 * 전체 세션 대화 내보내기 (다운로드)
 */
export function exportAllSessionsUrl(format: ExportFormat = "markdown"): string {
  return `${API_BASE_URL}/api/sessions/export/all?format=${format}`;
}

/**
 * 단일 세션 대화를 파일로 다운로드
 */
export async function downloadSessionExport(sessionId: string, format: ExportFormat): Promise<void> {
  const url = exportSessionUrl(sessionId, format);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition");
  const filename = contentDisposition
    ? contentDisposition.split("filename=")[1]?.replace(/"/g, "")
    : `session-${sessionId.slice(0, 8)}.${format === "markdown" ? "md" : format}`;

  // 브라우저 다운로드 트리거
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

/**
 * 전체 세션 대화를 파일로 다운로드
 */
export async function downloadAllSessionsExport(format: ExportFormat): Promise<void> {
  const url = exportAllSessionsUrl(format);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Export failed: ${response.status} ${response.statusText}`);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get("Content-Disposition");
  const filename = contentDisposition
    ? contentDisposition.split("filename=")[1]?.replace(/"/g, "")
    : `conversations-all.${format === "markdown" ? "md" : format}`;

  // 브라우저 다운로드 트리거
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

// ── 워크스페이스 ──────────────────────────────────────────────────────────

export interface Workspace {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  vector_collection: string;
  document_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreate {
  name: string;
  description?: string;
  system_prompt?: string;
}

export interface WorkspaceUpdate {
  name?: string;
  description?: string;
  system_prompt?: string;
}

export interface WorkspaceListResponse {
  workspaces: Workspace[];
  total: number;
}

export async function listWorkspaces(): Promise<WorkspaceListResponse> {
  return fetchAPI<WorkspaceListResponse>("/api/workspaces");
}

export async function createWorkspace(data: WorkspaceCreate): Promise<Workspace> {
  return fetchAPI<Workspace>("/api/workspaces", { method: "POST", body: JSON.stringify(data) });
}

export async function getWorkspace(id: string): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${id}`);
}

export async function updateWorkspace(id: string, data: WorkspaceUpdate): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteWorkspace(id: string): Promise<{ message: string; workspace_id: string }> {
  return fetchAPI(`/api/workspaces/${id}`, { method: "DELETE" });
}

export async function assignDocuments(workspaceId: string, documentIds: string[]): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${workspaceId}/documents`, {
    method: "POST",
    body: JSON.stringify({ document_ids: documentIds, action: "assign" }),
  });
}

export async function unassignDocuments(workspaceId: string, documentIds: string[]): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${workspaceId}/documents`, {
    method: "DELETE",
    body: JSON.stringify({ document_ids: documentIds, action: "unassign" }),
  });
}

// ── 음성 인터페이스 ──────────────────────────────────────────────────────

export interface STTResponse {
  text: string;
  language: string;
  duration_seconds?: number;
  provider: string;
}

export interface VoiceStatus {
  stt_provider: string | null;
  tts_provider: string | null;
  message: string;
}

/**
 * 음성 → 텍스트 변환 (서버 Whisper API)
 * 브라우저 Web Speech API를 사용할 수 없을 때 폴백으로 사용
 */
export async function speechToText(audioBlob: Blob, language = "ko"): Promise<STTResponse> {
  const formData = new FormData();
  formData.append("file", audioBlob, "recording.webm");
  return fetchAPI<STTResponse>(`/api/voice/stt?language=${language}`, {
    method: "POST",
    body: formData,
    headers: {}, // Content-Type은 브라우저가 multipart로 설정
  });
}

/**
 * 텍스트 → 음성 변환 (서버 ElevenLabs API)
 * MP3 오디오 Blob을 반환합니다
 */
export async function textToSpeech(
  text: string,
  options?: { voiceId?: string; speed?: number }
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/voice/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      voice_id: options?.voiceId,
      language: "ko",
      speed: options?.speed ?? 1.0,
    }),
  });

  if (!response.ok) {
    throw new Error(`TTS API error: ${response.status} ${response.statusText}`);
  }

  return response.blob();
}

/**
 * 음성 API 상태 확인
 */
export async function getVoiceStatus(): Promise<VoiceStatus> {
  return fetchAPI<VoiceStatus>("/api/voice");
}

// ── 시스템 프롬프트 ──────────────────────────────────────────────────────

export type PromptMode = "fact" | "summary" | "column" | "reasoning" | "creative";

export interface SystemPrompt {
  id: string;
  workspace_id: string | null;
  mode: PromptMode;
  prompt_text: string;
  variables: string[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface SystemPromptCreate {
  workspace_id?: string | null;
  mode: PromptMode;
  prompt_text: string;
  is_default?: boolean;
}

export interface SystemPromptUpdate {
  prompt_text?: string;
  is_default?: boolean;
}

export interface SystemPromptPreview {
  id: string;
  mode: PromptMode;
  workspace_id: string | null;
  original_text: string;
  rendered_text: string;
  variables_used: string[];
  variables_missing: string[];
}

export interface SystemPromptListResponse {
  prompts: SystemPrompt[];
  total: number;
}

export interface SupportedVariables {
  variables: Record<string, string>;
}

export async function listPrompts(params?: {
  workspace_id?: string;
  mode?: PromptMode;
}): Promise<SystemPromptListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.workspace_id) searchParams.set("workspace_id", params.workspace_id);
  if (params?.mode) searchParams.set("mode", params.mode);
  const qs = searchParams.toString();
  return fetchAPI<SystemPromptListResponse>(`/api/prompts${qs ? `?${qs}` : ""}`);
}

export async function createPrompt(data: SystemPromptCreate): Promise<SystemPrompt> {
  return fetchAPI<SystemPrompt>("/api/prompts", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getPrompt(id: string): Promise<SystemPrompt> {
  return fetchAPI<SystemPrompt>(`/api/prompts/${id}`);
}

export async function updatePrompt(id: string, data: SystemPromptUpdate): Promise<SystemPrompt> {
  return fetchAPI<SystemPrompt>(`/api/prompts/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deletePrompt(id: string): Promise<{ message: string; id: string }> {
  return fetchAPI(`/api/prompts/${id}`, { method: "DELETE" });
}

export async function previewPrompt(id: string, workspace_id?: string): Promise<SystemPromptPreview> {
  const searchParams = new URLSearchParams();
  if (workspace_id) searchParams.set("workspace_id", workspace_id);
  const qs = searchParams.toString();
  return fetchAPI<SystemPromptPreview>(`/api/prompts/${id}/preview${qs ? `?${qs}` : ""}`, {
    method: "POST",
  });
}

export async function listDefaultPrompts(): Promise<SystemPromptListResponse> {
  return fetchAPI<SystemPromptListResponse>("/api/prompts/defaults");
}

export async function listSupportedVariables(): Promise<SupportedVariables> {
  return fetchAPI<SupportedVariables>("/api/prompts/variables");
}

// ── 에이전트 모드 ─────────────────────────────────────────────────────────

export interface AgentToolInfo {
  name: string;
  description: string;
  parameters: Array<{ name: string; type: string; description: string; required: boolean }>;
}

export interface AgentStep {
  type: "thinking" | "tool_call" | "tool_result";
  content: string;
  tool_name?: string;
  tool_success?: boolean;
  tool_display?: Record<string, unknown>;
}

export interface AgentResponse {
  answer: string;
  steps: AgentStep[];
  tool_calls: AgentStep[];
  is_agent: boolean;
}

/** 개별 툴 실행 결과 (ChatInterface에서 사용) */
export type AgentToolResult = AgentStep;

export async function listAgentTools(): Promise<AgentToolInfo[]> {
  return fetchAPI<AgentToolInfo[]>("/api/chat/agent/tools");
}

// Agent mode uses the normal chatApi with @agent prefix — the backend
// detects it and returns AgentResponse instead of ChatResponse.


// ── API 키 관리 ────────────────────────────────────────────────────────────

export interface ApiKeyCreateRequest {
  name: string;
  description?: string;
  rate_limit?: number;
}

export interface ApiKeyResponse {
  id: string;
  name: string;
  description: string | null;
  key_prefix: string;
  rate_limit: number;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
  usage_count: number;
}

export interface ApiKeyCreateResponse extends ApiKeyResponse {
  api_key: string; // 평문 키 — 생성 시 1회만 노출
}

export async function listApiKeys(): Promise<ApiKeyResponse[]> {
  return fetchAPI<ApiKeyResponse[]>("/api/api-keys");
}

export async function createApiKey(req: ApiKeyCreateRequest): Promise<ApiKeyCreateResponse> {
  return fetchAPI<ApiKeyCreateResponse>("/api/api-keys", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export async function getApiKey(keyId: string): Promise<ApiKeyResponse> {
  return fetchAPI<ApiKeyResponse>(`/api/api-keys/${keyId}`);
}

export async function rotateApiKey(keyId: string): Promise<ApiKeyCreateResponse> {
  return fetchAPI<ApiKeyCreateResponse>(`/api/api-keys/${keyId}/rotate`, {
    method: "POST",
  });
}

export async function deactivateApiKey(keyId: string): Promise<ApiKeyResponse> {
  return fetchAPI<ApiKeyResponse>(`/api/api-keys/${keyId}/deactivate`, {
    method: "POST",
  });
}

export async function deleteApiKey(keyId: string): Promise<{ ok: boolean; message: string }> {
  return fetchAPI(`/api/api-keys/${keyId}`, { method: "DELETE" });
}


// ── 외부용 v1 챗 API 클라이언트 ──────────────────────────────────────────────

export interface V1ChatRequest {
  question: string;
  mode: ChatMode;
  session_id?: string;
  reasoning_strength?: ReasoningStrength;
  workspace_id?: string;
}

export interface V1ChatResponse {
  answer: string;
  sources: Array<{ source: string; text: string; score: number; page?: number }> | null;
  mode: string;
  session_id: string;
}

/** 외부용 v1 채팅 API — apiKey를 직접 전달하여 X-API-Key 헤더로 인증 */
export async function v1ChatApi(
  req: V1ChatRequest,
  apiKey: string,
  baseUrl: string = "",
): Promise<V1ChatResponse> {
  const url = `${baseUrl || ""}/api/v1/chat`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`v1 API 오류 (${res.status}): ${detail}`);
  }

  return res.json();
}

/** 외부용 v1 모드 목록 */
export async function v1ListModes(
  apiKey: string,
  baseUrl: string = "",
): Promise<{ modes: Array<{ key: string; label: string }> }> {
  const url = `${baseUrl || ""}/api/v1/modes`;
  const res = await fetch(url, {
    headers: { "X-API-Key": apiKey },
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`v1 모드 목록 오류 (${res.status}): ${detail}`);
  }

  return res.json();
}


// ── 관리자: 사용자 관리 ──────────────────────────────────────────────────────

export interface AdminUser {
  id: string;
  username: string;
  display_name: string | null;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export async function listUsers(): Promise<AdminUser[]> {
  return fetchAPI<AdminUser[]>("/api/admin/users");
}

export async function getUser(userId: string): Promise<AdminUser> {
  return fetchAPI<AdminUser>(`/api/admin/users/${userId}`);
}

export async function updateUserRole(userId: string, role: "admin" | "user"): Promise<AdminUser> {
  return fetchAPI<AdminUser>(`/api/admin/users/${userId}/role`, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}

export async function setUserActive(userId: string, isActive: boolean): Promise<AdminUser> {
  return fetchAPI<AdminUser>(`/api/admin/users/${userId}/active`, {
    method: "PUT",
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function deleteUser(userId: string): Promise<{ ok: boolean; message: string }> {
  return fetchAPI(`/api/admin/users/${userId}`, { method: "DELETE" });
}

export async function getUserStats(): Promise<{
  total: number;
  active: number;
  admins: number;
  regular_users: number;
}> {
  return fetchAPI("/api/admin/users/stats/summary");
}

// ── 지식 그래프 ──────────────────────────────────────────────────────────

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  description?: string;
  mention_count: number;
  group: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  relation_type: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: Record<string, number>;
}

export interface KGStats {
  total_entities: number;
  total_relations: number;
  entities_by_type: Record<string, number>;
}

export interface EntitySearchResult {
  id: string;
  name: string;
  type: string;
  description?: string;
  mention_count: number;
  score: number;
}

export async function fetchKGGraph(
  documentId?: string,
  entityTypes?: string,
  limit: number = 200,
): Promise<GraphData> {
  const params = new URLSearchParams();
  if (documentId) params.set("document_id", documentId);
  if (entityTypes) params.set("entity_types", entityTypes);
  params.set("limit", String(limit));
  return fetchAPI(`/api/kg/graph?${params.toString()}`);
}

export async function fetchKGStats(): Promise<KGStats> {
  return fetchAPI("/api/kg/stats");
}

export async function extractKnowledgeGraph(documentId: string): Promise<unknown> {
  return fetchAPI("/api/kg/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId }),
  });
}

export async function searchKGEntities(
  query: string,
  entityTypes?: string,
  limit: number = 20,
): Promise<EntitySearchResult[]> {
  const params = new URLSearchParams();
  params.set("query", query);
  if (entityTypes) params.set("entity_types", entityTypes);
  params.set("limit", String(limit));
  const result = await fetchAPI<{ query: string; results: EntitySearchResult[] }>(
    `/api/kg/search?${params.toString()}`
  );
  return result.results;
}

export async function fetchKGEntityDetail(entityId: string): Promise<Record<string, unknown>> {
  return fetchAPI(`/api/kg/entity/${entityId}`);
}

