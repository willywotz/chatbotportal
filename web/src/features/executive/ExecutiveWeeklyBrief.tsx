import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { RefreshCw, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";

interface Props {
  weeklyBrief: string | null;
  canRegenerate?: boolean;
  isRegenerating?: boolean;
  onRegenerate?: () => void;
}

export function ExecutiveWeeklyBrief({ weeklyBrief, canRegenerate, isRegenerating, onRegenerate }: Props) {
  return (
    <Card className="border bg-white">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-primary/10">
              <Sparkles className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-lg">AI Weekly Executive Brief</CardTitle>
              <CardDescription>วิเคราะห์โดย AI สำหรับผู้บริหาร</CardDescription>
            </div>
          </div>
          {canRegenerate && (
            <Button variant="outline" size="sm" onClick={onRegenerate} disabled={isRegenerating}>
              <RefreshCw className={`h-4 w-4 ${isRegenerating ? "animate-spin" : ""}`} />
              {isRegenerating ? "กำลังสร้างใหม่..." : "สร้างใหม่"}
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="prose prose-sm dark:prose-invert max-w-none text-foreground">
          {weeklyBrief ? (
            <ReactMarkdown>{weeklyBrief}</ReactMarkdown>
          ) : (
            <p className="text-muted-foreground">กำลังสร้างรายงานสรุป...</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
