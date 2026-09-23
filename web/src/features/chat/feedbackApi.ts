import { api } from '@/shared/lib/apiClient';

export async function updateMessageRating(
  messageId: string,
  rating: 'up' | 'down',
  feedbackText?: string
): Promise<boolean> {
  try {
    await api.patch(`/api/v1/messages/${messageId}/rating`, {
      rating,
      feedback_text: feedbackText ?? null,
    });
    return true;
  } catch (err) {
    console.warn('Failed to update rating:', err);
    return false;
  }
}

export interface FeedbackStats {
  totalRatings: number;
  upCount: number;
  downCount: number;
  satisfactionRate: number;
  dailyTrend: { date: string; up: number; down: number; rate: number }[];
  lowRatedQuestions: { content: string; feedback_text: string | null; agency: string; created_at: string }[];
  agencyBreakdown: { agency: string; up: number; down: number; rate: number }[];
}

export async function fetchFeedbackStats(): Promise<FeedbackStats> {
  // Backend returns snake_case — map to camelCase expected by existing components
  const raw = await api.get<{
    total_ratings: number;
    up_count: number;
    down_count: number;
    satisfaction_rate: number;
    daily_trend: { date: string; up: number; down: number; rate: number }[];
    low_rated_questions: { content: string; feedback_text: string | null; agency: string; created_at: string }[];
    agency_breakdown: { agency: string; up: number; down: number; rate: number }[];
  }>('/api/v1/feedback/statistics');

  return {
    totalRatings: raw.total_ratings,
    upCount: raw.up_count,
    downCount: raw.down_count,
    satisfactionRate: raw.satisfaction_rate,
    dailyTrend: raw.daily_trend,
    lowRatedQuestions: raw.low_rated_questions,
    agencyBreakdown: raw.agency_breakdown,
  };
}
