import { AlertCircle, ThumbsDown, ThumbsUp, TrendingUp } from "lucide-react";

import { useFeedbackStats } from "@/features/feedback/useFeedbackStats";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { cn } from "@/shared/lib/utils";

export function FeedbackSummaryCards() {
  const { data: stats, isLoading, isError, refetch } = useFeedbackStats();

  if (isError) {
    return (
      <div role="alert" aria-live="assertive" className="flex items-center gap-2 text-destructive text-sm px-1 py-2">
        <AlertCircle className="h-4 w-4 shrink-0" />
        <span>โหลดข้อมูล Feedback ไม่สำเร็จ</span>
        <Button variant="outline" size="sm" className="ml-2 h-7 text-xs" onClick={() => void refetch()}>ลองอีกครั้ง</Button>
      </div>
    );
  }

  if (isLoading || !stats) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }

  const cards = [
    { label: "Feedback ทั้งหมด", value: stats.totalRatings, icon: TrendingUp, color: "text-primary" },
    { label: "👍 พึงพอใจ", value: stats.upCount, icon: ThumbsUp, color: "text-success" },
    { label: "👎 ไม่พึงพอใจ", value: stats.downCount, icon: ThumbsDown, color: "text-destructive" },
    { label: "อัตราความพึงพอใจ", value: `${stats.satisfactionRate}%`, icon: TrendingUp, color: "text-info" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((s, i) => (
        <Card key={i}>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <s.icon className={cn("h-4 w-4", s.color)} />
            </div>
            <p className="text-2xl font-bold text-foreground">{s.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
