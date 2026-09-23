const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

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
    const rand = seeded(now.getFullYear() * 100 + week + 7);

    // Topic clusters with week-over-week change
    const topicClusters = [
      { topic: 'การยื่นภาษีบุคคลธรรมดา', category: 'ภาษี', count: 4280, prevCount: 2150, sentiment: 'neutral' },
      { topic: 'ทำบัตรประชาชน/ต่ออายุ', category: 'ทะเบียนราษฎร', count: 3120, prevCount: 2980, sentiment: 'positive' },
      { topic: 'สิทธิลดหย่อนภาษี Easy E-Receipt', category: 'ภาษี', count: 2890, prevCount: 1240, sentiment: 'neutral' },
      { topic: 'ขอเลขทะเบียน อย.', category: 'อาหารและยา', count: 1950, prevCount: 1880, sentiment: 'neutral' },
      { topic: 'ราคาประเมินที่ดินรายแปลง', category: 'ที่ดิน', count: 1620, prevCount: 1750, sentiment: 'negative' },
      { topic: 'แจ้งย้ายที่อยู่ออนไลน์', category: 'ทะเบียนราษฎร', count: 1340, prevCount: 920, sentiment: 'positive' },
      { topic: 'การคืนภาษี', category: 'ภาษี', count: 1180, prevCount: 1100, sentiment: 'neutral' },
      { topic: 'ตรวจสอบสิทธิ์โฉนดที่ดิน', category: 'ที่ดิน', count: 980, prevCount: 1020, sentiment: 'neutral' },
    ].map(t => ({
      ...t,
      change: parseFloat((((t.count - t.prevCount) / t.prevCount) * 100).toFixed(1)),
    }));

    // Sentiment distribution
    const sentimentDist = {
      positive: 62 + Math.floor(rand() * 8),
      neutral: 28 + Math.floor(rand() * 5),
      negative: 5 + Math.floor(rand() * 4),
    };

    // No-answer rate by agency
    const noAnswerByAgency = [
      { agency: 'อย.', rate: 4.2 + rand() * 2 },
      { agency: 'กรมสรรพากร', rate: 2.1 + rand() * 1.5 },
      { agency: 'กรมการปกครอง', rate: 6.8 + rand() * 2 },
      { agency: 'กรมที่ดิน', rate: 8.5 + rand() * 2.5 },
    ].map(a => ({ ...a, rate: parseFloat(a.rate.toFixed(1)) }));

    // Daily question volume (last 7 days)
    const dayLabels = ['จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.', 'อา.'];
    const dailyVolume = dayLabels.map((day, i) => ({
      day,
      questions: Math.floor(5800 + i * 200 + rand() * 1500 - (i >= 5 ? 2000 : 0)),
    }));

    const totalWeekQuestions = dailyVolume.reduce((sum, d) => sum + d.questions, 0);
    const trendingTopics = topicClusters.filter(t => t.change > 30);
    const decliningTopics = topicClusters.filter(t => t.change < -10);

    // AI-generated insights via Lovable AI
    let aiInsights = '';
    let recommendations: string[] = [];
    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');

    if (LOVABLE_API_KEY) {
      try {
        const prompt = `วิเคราะห์ข้อมูลการใช้งาน AI Portal ภาครัฐในสัปดาห์นี้ และสรุปเป็น insights เชิงกลยุทธ์สำหรับ Admin
ข้อมูลคำถามรายสัปดาห์:
- คำถามทั้งหมด: ${totalWeekQuestions.toLocaleString()} ข้อความ
- หัวข้อยอดนิยม Top 3: ${topicClusters.slice(0, 3).map(t => `${t.topic} (${t.count.toLocaleString()} ครั้ง, ${t.change > 0 ? '+' : ''}${t.change}%)`).join(', ')}
- หัวข้อมาแรง (เพิ่มขึ้น >30%): ${trendingTopics.map(t => `${t.topic} (+${t.change}%)`).join(', ') || 'ไม่มี'}
- Sentiment: บวก ${sentimentDist.positive}%, กลาง ${sentimentDist.neutral}%, ลบ ${sentimentDist.negative}%
- No-answer rate สูงสุด: ${noAnswerByAgency.sort((a,b)=>b.rate-a.rate)[0].agency} (${noAnswerByAgency[0].rate}%)
กรุณาตอบในรูปแบบ JSON ผ่าน function call ที่เตรียมไว้`;

        const aiRes = await fetch('https://ai.gateway.lovable.dev/v1/chat/completions', {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${LOVABLE_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'google/gemini-2.5-flash',
            messages: [
              { role: 'system', content: 'คุณเป็นนักวิเคราะห์ข้อมูลภาครัฐที่เชี่ยวชาญด้าน citizen experience' },
              { role: 'user', content: prompt },
            ],
            tools: [{
              type: 'function',
              function: {
                name: 'submit_insights',
                description: 'ส่ง insights และข้อเสนอแนะ',
                parameters: {
                  type: 'object',
                  properties: {
                    summary: { type: 'string', description: 'สรุป insight หลัก 2-3 ย่อหน้า ภาษาไทย' },
                    recommendations: {
                      type: 'array',
                      items: { type: 'string' },
                      description: 'ข้อเสนอแนะ 3-5 ข้อ แต่ละข้อสั้น กระชับ ปฏิบัติได้',
                    },
                  },
                  required: ['summary', 'recommendations'],
                  additionalProperties: false,
                },
              },
            }],
            tool_choice: { type: 'function', function: { name: 'submit_insights' } },
          }),
        });

        if (aiRes.ok) {
          const data = await aiRes.json();
          const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];
          if (toolCall) {
            const args = JSON.parse(toolCall.function.arguments);
            aiInsights = args.summary || '';
            recommendations = args.recommendations || [];
          }
        } else if (aiRes.status === 429) {
          aiInsights = '⚠️ ระบบ AI กำลังประมวลผลคำขอจำนวนมาก กรุณาลองใหม่ภายหลัง';
        } else if (aiRes.status === 402) {
          aiInsights = '⚠️ เครดิต AI หมด กรุณาติดต่อผู้ดูแลระบบ';
        }
      } catch (e) {
        console.error('AI insights error:', e);
        aiInsights = 'ไม่สามารถสร้าง insights ได้ในขณะนี้';
      }
    }

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          totalWeekQuestions,
          topicClusters,
          sentimentDist,
          noAnswerByAgency,
          dailyVolume,
          trendingTopics,
          decliningTopics,
          aiInsights,
          recommendations,
          generatedAt: now.toISOString(),
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (e) {
    console.error('analytics-insights error:', e);
    return new Response(
      JSON.stringify({ success: false, error: e instanceof Error ? e.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});