import { fetchAPI } from "./api";

// ── Cross-Document Reasoning API ─────────────────────────────────────────

export interface SubQuery {
  id: string;
  query: string;
  parent_query: string;
  sources: string[];
  answer: string;
  confidence: number;
}

export interface ConflictPoint {
  topic: string;
  conflict_type: "contradiction" | "partial" | "complementary" | "tension";
  source_a: string;
  source_b: string;
  claim_a: string;
  claim_b: string;
  explanation: string;
  severity: number;
}

export interface ConsensusPoint {
  topic: string;
  sources: string[];
  consensus: string;
  strength: number;
}

export interface CrossAnalysis {
  id: string;
  original_query: string;
  mode: string;
  sub_queries: SubQuery[];
  conflicts: ConflictPoint[];
  consensuses: ConsensusPoint[];
  synthesis: string;
  confidence_score: number;
  status: "pending" | "analyzing" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
}

export interface CrossAnalysisRequest {
  query: string;
  mode?: string;
  max_sub_queries?: number;
}

export async function analyzeCrossDocument(request: CrossAnalysisRequest): Promise<CrossAnalysis> {
  return fetchAPI<CrossAnalysis>("/api/cross-reasoning/analyze", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listCrossAnalyses(): Promise<CrossAnalysis[]> {
  return fetchAPI<CrossAnalysis[]>("/api/cross-reasoning/analyses");
}

export async function getCrossAnalysis(id: string): Promise<CrossAnalysis> {
  return fetchAPI<CrossAnalysis>(`/api/cross-reasoning/analyses/${id}`);
}