import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

  try {
    const url = new URL(req.url);
    const rangeParam = url.searchParams.get('range') || '7d';
    const days = rangeParam === '30d' ? 30 : rangeParam === '90d' ? 90 : 7;

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    );

    const since = new Date(Date.now() - days * 86400000).toISOString();

    const { data: convs, error } = await supabase
      .from('conversations')
      .select('id, agencies, created_at, message_count')
      .gte('created_at', since)
      .limit(10000);

    if (error) throw error;

    const dayNames = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'];
    const orderedDays = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์'];
    const hours = Array.from({ length: 24 }, (_, i) => i);

    const knownAgencies = [
      { id: 'fda', name: 'อย.', match: ['fda', 'อย', 'อาหาร'] },
      { id: 'revenue', name: 'กรมสรรพากร', match: ['revenue', 'สรรพากร', 'ภาษี'] },
      { id: 'dopa', name: 'กรมการปกครอง', match: ['dopa', 'ปกครอง', 'ทะเบียน'] },
      { id: 'land', name: 'กรมที่ดิน', match: ['land', 'ที่ดิน', 'โฉนด'] },
    ];

    function classifyAgency(tags: string[]): string | null {
      const joined = (tags || []).join(' ').toLowerCase();
      for (const a of knownAgencies) {
        if (a.match.some(m => joined.includes(m.toLowerCase()))) return a.id;
      }
      return null;
    }

    // Init matrices
    const dayHourCounts: number[][] = orderedDays.map(() => hours.map(() => 0));
    const agencyHourCounts: Record<string, number[]> = {};
    knownAgencies.forEach(a => { agencyHourCounts[a.id] = hours.map(() => 0); });

    let totalMessages = 0;
    const rows = convs || [];

    rows.forEach((c: any) => {
      const d = new Date(c.created_at);
      const hour = d.getHours();
      const jsDayIdx = d.getDay(); // 0=Sun
      const dayName = dayNames[jsDayIdx];
      const orderedIdx = orderedDays.indexOf(dayName);
      const weight = c.message_count || 1;
      totalMessages += weight;

      if (orderedIdx >= 0) dayHourCounts[orderedIdx][hour] += weight;

      const agencyTags = Array.isArray(c.agencies) ? c.agencies : [];
      // Prefer explicit tags
      const matched = agencyTags.map((t: string) => classifyAgency([t])).filter(Boolean);
      if (matched.length === 0) {
        const fallback = classifyAgency(agencyTags);
        if (fallback) agencyHourCounts[fallback][hour] += weight;
      } else {
        matched.forEach((id: string) => { agencyHourCounts[id][hour] += weight; });
      }
    });

    const dayHourMatrix = orderedDays.map((day, di) => ({
      day,
      dayIndex: di,
      data: dayHourCounts[di],
    }));

    const hourlyByAgency = knownAgencies.map(a => ({
      agency: a.name,
      agencyId: a.id,
      data: agencyHourCounts[a.id],
    }));

    // Peak insights
    let peakValue = 0;
    let peakDay = '-';
    let peakHour = 0;
    dayHourMatrix.forEach(row => {
      row.data.forEach((v, h) => {
        if (v > peakValue) {
          peakValue = v;
          peakDay = row.day;
          peakHour = h;
        }
      });
    });

    const businessHoursTotal = dayHourMatrix.reduce(
      (sum, row) => sum + row.data.slice(8, 18).reduce((s, v) => s + v, 0),
      0
    );
    const totalRequests = dayHourMatrix.reduce(
      (sum, row) => sum + row.data.reduce((s, v) => s + v, 0),
      0
    );
    const businessHoursPercent = totalRequests > 0
      ? parseFloat(((businessHoursTotal / totalRequests) * 100).toFixed(1))
      : 0;

    const agencyTotals = hourlyByAgency.map(a => ({
      agency: a.agency,
      total: a.data.reduce((s, v) => s + v, 0),
      peakHour: a.data.indexOf(Math.max(...a.data)),
    }));
    const busiest = agencyTotals.sort((a, b) => b.total - a.total)[0] || { agency: '-', total: 0, peakHour: 0 };

    const recommendation = totalRequests === 0
      ? 'ยังไม่มีข้อมูลคำถามในช่วงเวลานี้ เริ่มใช้งานระบบเพื่อสร้างข้อมูลวิเคราะห์'
      : peakHour >= 9 && peakHour <= 11
        ? 'ควรเตรียมกำลังคน Call Center สำรองช่วงเช้า (09:00-11:00) และเพิ่ม capacity ของ API agencies ใน peak window'
        : peakHour >= 13 && peakHour <= 16
          ? 'Peak load ช่วงบ่าย ควรปรับ rate limit และเตรียม scaling อัตโนมัติช่วง 13:00-16:00'
          : 'ควรกระจายโหลดด้วย caching และ async queue ในช่วง peak';

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          range: rangeParam,
          days,
          sampleSize: rows.length,
          totalMessages,
          days_labels: orderedDays,
          hours,
          agencies: knownAgencies.map(a => ({ id: a.id, name: a.name })),
          hourlyByAgency,
          dayHourMatrix,
          insights: {
            peakDay,
            peakHour: `${String(peakHour).padStart(2, '0')}:00`,
            peakValue,
            totalRequests,
            businessHoursPercent,
            busiest,
            recommendation,
          },
          generatedAt: new Date().toISOString(),
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (e) {
    console.error('usage-heatmap error:', e);
    return new Response(
      JSON.stringify({ success: false, error: e instanceof Error ? e.message : 'Unknown' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});