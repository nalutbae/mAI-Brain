// ── Human-in-the-Loop RAG Feedback API ──────────────────────────────────

import { fetchAPI } from "./api";

// ── Types ────────────────────────────────────────────────────────────────

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
  recent_trend: { positive: number; negative: number };
}

// ── Tag labels ────────────────────────────────────────────────────────────

export const TAG_LABELS: Record<FeedbackTag, string> = {
  irrelevant: "관련 없음",
  incomplete: "불완전",
  outdated: "구식 정보",
  hallucination: "환각 (사실과 다름)",
  wrong_source: "잘못된 출처",
  biased: "편향됨",
  unclear: "불분명함",
};

export const TAG_COLORS: Record<FeedbackTag, string> = {
  irrelevant: "text-orange-600 bg-orange-100 dark:text-orange-300 dark:bg-orange-900",
  incomplete: "text-yellow-600 bg-yellow-100 dark:text-yellow-300 dark:bg-yellow-900",
  outdated: "text-gray-600 bg-gray-100 dark:text-gray-300 dark:bg-gray-900",
  hallucination: "text-red-600 bg-red-100 dark:text-red-300 dark:bg-red-900",
  wrong_source: "text-pink-600 bg-pink-100 dark:text-pink-300 dark:bg-pink-900",
  biased: "text-purple-600 bg-purple-100 dark:text-purple-300 dark:bg-purple-900",
  unclear: "text-blue-600 bg-blue-100 dark:text-blue-300 dark:bg-blue-900",
};

// ── API ───────────────────────────────────────────────────────────────────

export async function submitFeedback(data: FeedbackCreate): Promise<Feedback> {
  return fetchAPI("/feedback", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function listFeedbacks(params?: {
  feedback_type?: FeedbackType;
  tags?: string;
  session_id?: string;
  limit?: number;
  offset?: number;
}): Promise<Feedback[]> {
  const query = new URLSearchParams();
  if (params?.feedback_type) query.set("feedback_type", params.feedback_type);
  if (params?.tags) query.set("tags", params.tags);
  if (params?.session_id) query.set("session_id", params.session_id);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const qs = query.toString();
  return fetchAPI(`/feedback${qs ? `?${qs}` : ""}`);
}

export async function getFeedbackStats(): Promise<FeedbackStats> {
  return fetchAPI("/feedback/stats");
}

export async function getSuggestions(): Promise<any[]> {
  return fetchAPI("/feedback/suggestions");
}

export async function deleteFeedback(id: string): Promise<void> {
  await fetchAPI(`/feedback/${id}`, { method: "DELETE" });
}