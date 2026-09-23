const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Deterministic pseudo-random based on ISO week so values are stable per week
function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

function getISOWeek(d: Date) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

  try {
    const now = new Date();
    const week = getISOWeek(now);
    const rand = seeded(now.getFullYear() * 100 + week);

    // Core KPIs with MoM / YoY
    const thisMonthQuestions = 48290 + Math.floor(rand() * 5000);
    const lastMonthQuestions = 42100 + Math.floor(rand() * 4000);
    const lastYearMonthQuestions = 28500 + Math.floor(rand() * 3000);

    const momGrowth = ((thisMonthQuestions - lastMonthQuestions) / lastMonthQuestions) * 100;
    const yoyGrowth = ((thisMonthQuestions - lastYearMonthQuestions) / lastYearMonthQuestions) * 100;

    const uniqueCitizens = Math.floor(thisMonthQuestions * 0.62);
    const avgMinutesSaved = 12; // vs call center
    const totalHoursSaved = Math.floor((thisMonthQuestions * avgMinutesSaved) / 60);
    const costPerCall = 45; // baht
    const costSaved = thisMonthQuestions * costPerCall;

    // Health score components
    const uptime = 99.2 + rand() * 0.7;
    const satisfaction = 93 + rand() * 4;
    const avgResponseTime = 2.0 + rand() * 0.6;
    const responseScore = Math.max(0, 100 - (avgResponseTime - 1) * 20);
    const healthScore = Math.round((uptime + satisfaction + responseScore) / 3);

    // Agency scorecard
    const agencyScorecard = [
      { name: 'อย.', shortName: 'FDA', uptime: 99.5, avgLatency: 245, satisfaction: 94.2, calls: 12450, grade: 'A' },
      { name: 'กรมสรรพากร', shortName: 'Revenue', uptime: 99.8, avgLatency: 180, satisfaction: 95.1, calls: 18320, grade: 'A' },
      { name: 'กรมการปกครอง', shortName: 'DOPA', uptime: 98.2, avgLatency: 420, satisfaction: 88.5, calls: 9870, grade: 'B' },
      { name: 'กรมที่ดิน', shortName: 'Land', uptime: 97.5, avgLatency: 510, satisfaction: 86.0, calls: 7650, grade: 'B' },
    ].map(a => ({
      ...a,
      uptime: parseFloat((a.uptime + (rand() - 0.5) * 0.5).toFixed(2)),
      avgLatency: a.avgLatency + Math.floor((rand() - 0.5) * 50),
      satisfaction: parseFloat((a.satisfaction + (rand() - 0.5) * 2).toFixed(1)),
    }));

    // Monthly trend (last 6 months)
    const months = ['พ.ย.', 'ธ.ค.', 'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.'];
    const monthlyTrend = months.map((m, i) => ({
      month: m,
      questions: Math.floor(20000 + i * 4500 + rand() * 3000),
      satisfaction: parseFloat((90 + i * 0.5 + rand() * 2).toFixed(1)),
    }));

    // Top issues (no-answer / hot topics)
    const topIssues = [
      { topic: 'การยื่นภาษีออนไลน์', count: 3420, trend: 'up' },
      { topic: 'ขั้นตอนทำบัตรประชาชน', count: 2890, trend: 'up' },
      { topic: 'การขอเลขทะเบียนยา', count: 1950, trend: 'stable' },
      { topic: 'ราคาประเมินที่ดิน', count: 1620, trend: 'down' },
      { topic: 'สิทธิลดหย่อนภาษี', count: 1480, trend: 'up' },
    ];

    // AI Weekly Brief via Lovable AI
    let weeklyBrief = '';
    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');
    if (LOVABLE_API_KEY) {
      try {
        const briefPrompt = `คุณเป็นนักวิเคราะห์ข้อมูลให้ผู้บริหารระดับสูงของรัฐบาลไทย กรุณาสรุปข้อมูลการใช้งาน AI Portal ในสัปดาห์นี้เป็นภาษาไทย ความยาว 3-4 ย่อหน้า เน้น insights เชิงกลยุทธ์และข้อเสนอแนะเชิงนโยบาย
ข้อมูล:
- คำถามรวมเดือนนี้: ${thisMonthQuestions.toLocaleString()} (เพิ่มขึ้น ${momGrowth.toFixed(1)}% จากเดือนก่อน, เพิ่มขึ้น ${yoyGrowth.toFixed(1)}% จากปีก่อน)
- ประชาชนที่ได้รับบริการ: ${uniqueCitizens.toLocaleString()} คน
- เวลาราชการที่ประหยัดได้: ${totalHoursSaved.toLocaleString()} ชั่วโมง
- งบประมาณที่ประหยัดได้: ${costSaved.toLocaleString()} บาท
- คะแนนสุขภาพระบบ: ${healthScore}/100
- หน่วยงานที่ใช้งานสูงสุด: ${agencyScorecard.sort((a,b)=>b.calls-a.calls)[0].name}
- หัวข้อที่ประชาชนถามบ่อย: ${topIssues.slice(0,3).map(t=>t.topic).join(', ')}
โครงสร้าง:
1. ภาพรวมและไฮไลท์สัปดาห์
2. แนวโน้มที่น่าสนใจและสาเหตุที่เป็นไปได้
3. ข้อเสนอแนะเชิงนโยบายสำหรับผู้บริหาร
ใช้ภาษาทางการ กระชับ ชัดเจน มี emoji ประกอบเล็กน้อย`;

        const aiRes = await fetch('https://ai.gateway.lovable.dev/v1/chat/completions', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${LOVABLE_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'google/gemini-2.5-flash',
            messages: [
              { role: 'system', content: 'คุณเป็นนักวิเคราะห์ข้อมูลภาครัฐ เขียนรายงานสำหรับผู้บริหารระดับสูง' },
              { role: 'user', content: briefPrompt },
            ],
          }),
        });

        if (aiRes.ok) {
          const data = await aiRes.json();
          weeklyBrief = data.choices?.[0]?.message?.content || '';
        } else if (aiRes.status === 429) {
          weeklyBrief = '⚠️ ระบบ AI กำลังประมวลผลคำขอจำนวนมาก กรุณาลองใหม่ภายหลัง';
        } else if (aiRes.status === 402) {
          weeklyBrief = '⚠️ เครดิต AI หมด กรุณาติดต่อผู้ดูแลระบบ';
        }
      } catch (e) {
        console.error('AI brief error:', e);
        weeklyBrief = 'ไม่สามารถสร้างรายงานสรุปได้ในขณะนี้';
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          kpis: {
            totalQuestions: thisMonthQuestions,
            momGrowth: parseFloat(momGrowth.toFixed(1)),
            yoyGrowth: parseFloat(yoyGrowth.toFixed(1)),
            uniqueCitizens,
            totalHoursSaved,
            costSaved,
            healthScore,
            uptime: parseFloat(uptime.toFixed(2)),
            satisfaction: parseFloat(satisfaction.toFixed(1)),
            avgResponseTime: parseFloat(avgResponseTime.toFixed(2)),
          },
          agencyScorecard,
          monthlyTrend,
          topIssues,
          weeklyBrief,
          generatedAt: now.toISOString(),
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (e) {
    console.error('executive-summary error:', e);
    return new Response(
      JSON.stringify({ success: false, error: e instanceof Error ? e.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});