const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();

  // Simulate processing
  await new Promise((r) => setTimeout(r, 200 + Math.random() * 200));

  const stats = {
    totalQuestions: 48290 + Math.floor(Math.random() * 50),
    todayQuestions: 150 + Math.floor(Math.random() * 20),
    avgResponseTime: `${(2.0 + Math.random() * 0.6).toFixed(1)} วินาที`,
    satisfactionRate: parseFloat((93.5 + Math.random() * 2).toFixed(1)),
  };

  const agencyUsage = [
    { name: 'อย.', value: 12450 + Math.floor(Math.random() * 100), fill: 'hsl(145 55% 40%)' },
    { name: 'กรมสรรพากร', value: 18320 + Math.floor(Math.random() * 100), fill: 'hsl(213 70% 45%)' },
    { name: 'กรมการปกครอง', value: 9870 + Math.floor(Math.random() * 100), fill: 'hsl(25 85% 55%)' },
    { name: 'กรมที่ดิน', value: 7650 + Math.floor(Math.random() * 100), fill: 'hsl(280 50% 50%)' },
  ];

  const weeklyTrend = [
    { day: 'จันทร์', questions: 170 + Math.floor(Math.random() * 30) },
    { day: 'อังคาร', questions: 200 + Math.floor(Math.random() * 30) },
    { day: 'พุธ', questions: 185 + Math.floor(Math.random() * 30) },
    { day: 'พฤหัสบดี', questions: 230 + Math.floor(Math.random() * 30) },
    { day: 'ศุกร์', questions: 210 + Math.floor(Math.random() * 30) },
    { day: 'เสาร์', questions: 80 + Math.floor(Math.random() * 30) },
    { day: 'อาทิตย์', questions: 55 + Math.floor(Math.random() * 30) },
  ];

  const categoryData = [
    { category: 'สอบถามข้อมูล', count: 22450 + Math.floor(Math.random() * 200) },
    { category: 'ตรวจสอบสถานะ', count: 12300 + Math.floor(Math.random() * 200) },
    { category: 'ขั้นตอนดำเนินการ', count: 8900 + Math.floor(Math.random() * 200) },
    { category: 'กฎหมาย/ระเบียบ', count: 4640 + Math.floor(Math.random() * 200) },
  ];

  return new Response(
    JSON.stringify({
      success: true,
      data: { stats, agencyUsage, weeklyTrend, categoryData },
      responseTime: Date.now() - start,
    }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
