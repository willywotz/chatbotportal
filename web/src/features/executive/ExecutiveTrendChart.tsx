import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";

interface MonthPoint { month: string; questions: number; satisfaction: number }
interface Props { monthlyTrend: MonthPoint[] }

export function ExecutiveTrendChart({ monthlyTrend }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">แนวโน้ม 12 เดือนย้อนหลัง</CardTitle>
        <CardDescription>จำนวนคำถามและความพึงพอใจ</CardDescription>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={280}>
          <LineChart data={monthlyTrend}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="month" stroke="hsl(var(--muted-foreground))" />
            <YAxis yAxisId="left" stroke="hsl(var(--muted-foreground))" />
            <YAxis yAxisId="right" orientation="right" stroke="hsl(var(--muted-foreground))" domain={[80, 100]} />
            <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }} />
            <Legend />
            <Line yAxisId="left" type="monotone" dataKey="questions" stroke="hsl(var(--primary))" strokeWidth={2} name="คำถาม" dot={{ r: 4 }} />
            <Line yAxisId="right" type="monotone" dataKey="satisfaction" stroke="hsl(var(--success))" strokeWidth={2} name="ความพึงพอใจ %" dot={{ r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
