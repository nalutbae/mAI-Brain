// ── Semantic Chunking Profiles API ────────────────────────────────────────

import { fetchAPI } from "./api";

// ── Types ────────────────────────────────────────────────────────────────

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

export interface ChunkPreview {
  profile_id: string;
  total_chunks: number;
  chunks: { text: string; length: number }[];
  avg_chunk_size: number;
  total_chars: number;
}

export interface ChunkPreviewRequest {
  text: string;
  profile_id?: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

// ── Strategy labels ──────────────────────────────────────────────────────

export const STRATEGY_LABELS: Record<ChunkingStrategy, string> = {
  fixed: "고정 크기",
  sentence: "문장 단위",
  paragraph: "단락 단위",
  section: "섹션 단위",
  article: "조문 단위",
};

export const STRATEGY_DESCRIPTIONS: Record<ChunkingStrategy, string> = {
  fixed: "지정된 글자 수로 균등 분할",
  sentence: "문장 경계에서 분할",
  paragraph: "빈 줄(단락) 경계에서 분할",
  section: "섹션 헤더 경계에서 분할 (논문 등)",
  article: "조/항 단위로 분할 (법률 문서 등)",
};

// ── API ───────────────────────────────────────────────────────────────────

export async function listProfiles(): Promise<ChunkingProfile[]> {
  return fetchAPI("/chunking/profiles");
}

export async function getProfile(profileId: string): Promise<ChunkingProfile> {
  return fetchAPI(`/chunking/profiles/${profileId}`);
}

export async function createProfile(data: ChunkingProfileCreate): Promise<ChunkingProfile> {
  return fetchAPI("/chunking/profiles", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProfile(
  profileId: string,
  data: Partial<ChunkingProfileCreate>,
): Promise<ChunkingProfile> {
  return fetchAPI(`/chunking/profiles/${profileId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteProfile(profileId: string): Promise<void> {
  await fetchAPI(`/chunking/profiles/${profileId}`, { method: "DELETE" });
}

export async function previewChunking(request: ChunkPreviewRequest): Promise<ChunkPreview> {
  return fetchAPI("/chunking/preview", {
    method: "POST",
    body: JSON.stringify(request),
  });
}