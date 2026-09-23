export interface DashboardStats {
  totalQuestions: number;
  totalQuestionsTrend: number;
  todayQuestions: number;
  todayQuestionsTrend: number;
  avgResponseTime: number;
  avgResponseTimeTrend: number;
  satisfactionRate: number;
  satisfactionRateTrend: number;
}

export interface AgencyUsageDatum {
  name: string;
  value: number;
  fill: string;
}

export interface WeeklyTrendDatum {
  day: string;
  questions: number;
}

export interface CategoryDatum {
  category: string;
  count: number;
}
