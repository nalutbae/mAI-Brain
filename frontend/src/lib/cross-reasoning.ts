import { fetchAPI } from "./api";

// ── Cross-Document Reasoning API ─────────────────────────────────────────

export type ConflictType =
  | "direct_contradiction"
  | "temporal_conflict"
  | "partial_disagreement"
  | "evidence_gap";

export interface DocumentConflict {
  conflict_type: ConflictType;
  description: string;
  document_a: string;
  document_b: string;
  claim_a: string;
  claim_b: string;
  severity: "low" | "medium" | "high";
  resolution_hint?: string;
}

export interface DocumentAgreement {
  description: string;
  documents: string[];
  theme: string;
  strength: "weak" | "moderate" | "strong";
}

export interface SubQuery {
  id: string;
  query: string;
  aspect: string;
  order: number;
}

export interface SubQueryResult {
  sub_query: SubQuery;
  hits: Array<{
    text: string;
    source: string;
    score: number;
    chunk_index?: number;
    page?: number;
  }>;
  summary: string;
}

export type CrossReasoningStatus =
  | "pending"
  | "analyzing"
  | "completed"
  | "failed";

export interface CrossReasoningReport {
  id: string;
  status: CrossReasoningStatus;
  original_query: string;
  sub_queries: SubQuery[];
  sub_query_results: SubQueryResult[];
  conflicts: DocumentConflict[];
  agreements: DocumentAgreement[];
  synthesis: string;
  confidence: number;
  mode: string;
  created_at: string;
}

export interface CrossReasoningRequest {
  query: string;
  mode?: string;
  session_id?: string;
  reasoning_strength?: string;
  sub_queries?: string[];
}

export interface CrossReasoningResponse {
  report: CrossReasoningReport;
  answer: string;
}

// ── API calls ───────────────────────────────────────────────────────────────

export async function analyzeCrossReasoning(
  request: CrossReasoningRequest
): Promise<CrossReasoningResponse> {
  return fetchAPI<CrossReasoningResponse>("/api/cross-reasoning/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function decomposeQuery(query: string): Promise<SubQuery[]> {
  return fetchAPI<SubQuery[]>(
    `/api/cross-reasoning/decompose?query=${encodeURIComponent(query)}`,
    { method: "POST" }
  );
}

export async function detectConflicts(
  query: string
): Promise<{
  query: string;
  conflicts: DocumentConflict[];
  agreements: DocumentAgreement[];
  sub_queries: SubQuery[];
}> {
  return fetchAPI(
    `/api/cross-reasoning/detect?query=${encodeURIComponent(query)}`,
    { method: "POST" }
  );
}