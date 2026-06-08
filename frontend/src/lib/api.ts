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
  return fetchAPI<Workspace>("/api/workspaces", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getWorkspace(id: string): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${id}`);
}

export async function updateWorkspace(id: string, data: WorkspaceUpdate): Promise<Workspace> {
  return fetchAPI<Workspace>(`/api/workspaces/${id}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
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