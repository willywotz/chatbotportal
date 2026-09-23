from pydantic import BaseModel
from typing import List
from datetime import datetime

class ExecutiveKPIs(BaseModel):
    totalQuestions: int
    momGrowth: float  # Month-over-Month growth percentage
    yoyGrowth: float  # Year-over-Year growth percentage
    uniqueCitizens: int
    totalHoursSaved: float
    costSaved: float
    healthScore: float
    uptime: float     # Percentage (e.g., 99.9)
    satisfaction: float
    avgResponseTime: float

    thisMonthQuestions: int
    lastMonthQuestions: int
    thisYearQuestions: int
    lastYearQuestions: int
    momGrowthQuestions: float
    yoyGrowthQuestions: float

    thisMonthCitizens: int
    lastMonthCitizens: int
    thisYearCitizens: int
    lastYearCitizens: int
    momGrowthCitizens: float
    yoyGrowthCitizens: float

class AgencyScore(BaseModel):
    name: str
    shortName: str
    uptime: float
    avgLatency: float
    satisfaction: float
    calls: int
    grade: str  # e.g., "A", "B+", "C"

class MonthlyTrend(BaseModel):
    month: str
    questions: int
    satisfaction: float

class TopIssue(BaseModel):
    topic: str
    count: int
    trend: str  # e.g., "up", "down", "stable"

class ExecutiveData(BaseModel):
    kpis: ExecutiveKPIs
    agencyScorecard: List[AgencyScore]
    monthlyTrend: List[MonthlyTrend]
    topIssues: List[TopIssue]
    weeklyBrief: str
    generatedAt: datetime