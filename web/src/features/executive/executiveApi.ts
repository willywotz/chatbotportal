import { api } from '@/shared/lib/apiClient';

export interface ExecutiveKPIs {
  totalQuestions: number;
  momGrowth: number;
  yoyGrowth: number;
  uniqueCitizens: number;
  totalHoursSaved: number;
  costSaved: number;
  healthScore: number;
  uptime: number;
  satisfaction: number;
  avgResponseTime: number;

  thisMonthQuestions: number;
  lastMonthQuestions: number;
  thisYearQuestions: number;
  lastYearQuestions: number;
  momGrowthQuestions: number;
  yoyGrowthQuestions: number;

  thisMonthCitizens: number;
  lastMonthCitizens: number;
  thisYearCitizens: number;
  lastYearCitizens: number;
  momGrowthCitizens: number;
  yoyGrowthCitizens: number;
}

export interface AgencyScore {
  name: string;
  shortName: string;
  uptime: number;
  avgLatency: number;
  satisfaction: number;
  calls: number;
  grade: string;
}

export interface ExecutiveData {
  kpis: ExecutiveKPIs;
  agencyScorecard: AgencyScore[];
  monthlyTrend: { month: string; questions: number; satisfaction: number }[];
  topIssues: { topic: string; count: number; trend: string }[];
  weeklyBrief: string;
  generatedAt: string;
}

export async function fetchExecutiveSummary(): Promise<ExecutiveData> {
  return api.get<ExecutiveData>('/api/v1/executive-summary');
}

export interface RegenerateBriefResult {
  weeklyBrief: string;
  status: string;
  generatedAt: string;
}

export async function regenerateExecutiveSummary(): Promise<RegenerateBriefResult> {
  return api.post<RegenerateBriefResult>('/api/v1/executive-summary/regenerate');
}