from pydantic import BaseModel
from typing import List, Literal, Dict, Union, Any
from datetime import datetime

SentimentType = Literal['positive', 'neutral', 'negative']
StatusType = Literal['healthy', 'degraded', 'down']
SeverityType = Literal['info', 'warning', 'critical']
HeatmapRange = Literal['7d', '30d', '90d']


class TopicCluster(BaseModel):
    topic: str
    category: str
    count: int
    prevCount: int
    change: float  # Using float for changes/percentages
    sentiment: SentimentType

class AnalyticsInsightsData(BaseModel):
    totalWeekQuestions: int
    topicClusters: List[TopicCluster]
    sentimentDist: Dict[str, int]  # Keys: positive, neutral, negative
    noAnswerByAgency: List[Dict[str, Union[str, float]]]
    dailyVolume: List[Dict[str, Union[str, int]]]
    trendingTopics: List[TopicCluster]
    decliningTopics: List[TopicCluster]
    aiInsights: str
    recommendations: List[str]
    generatedAt: datetime  # Pydantic handles ISO strings automatically

class Agency(BaseModel):
    id: str
    name: str
    shortName: str
    status: StatusType
    uptime: float
    currentLatency: float
    avgLatency: float
    errorRate: float
    requestsPerMin: float
    lastCheckedAt: datetime

class Incident(BaseModel):
    agency: str
    type: str
    severity: SeverityType
    message: str
    occurredAt: datetime
    resolvedAt: Union[datetime, None] = None  # Optional if not yet resolved

class SLACompliance(BaseModel):
    agency: str
    uptime: float
    target: float
    met: bool

class AgencyHealthData(BaseModel):
    agencies: List[Agency]
    historical: List[Dict[str, Any]]
    incidents: List[Incident]
    slaCompliance: List[SLACompliance]
    generatedAt: datetime

class BusiestInsight(BaseModel):
    agency: str
    total: int
    peakHour: int

class HeatmapInsights(BaseModel):
    peakDay: str
    peakHour: str
    peakValue: int
    totalRequests: int
    businessHoursPercent: float
    busiest: BusiestInsight
    recommendation: str

class HourlyByAgency(BaseModel):
    agency: str
    agencyId: str
    data: List[int]

class DayHourMatrix(BaseModel):
    day: str
    dayIndex: int
    data: List[int]

class UsageHeatmapData(BaseModel):
    range: HeatmapRange
    days: int
    sampleSize: int
    totalMessages: int
    days_labels: List[str]
    hours: List[int]
    agencies: List[Dict[str, str]]
    hourlyByAgency: List[HourlyByAgency]
    dayHourMatrix: List[DayHourMatrix]
    insights: HeatmapInsights
    generatedAt: datetime