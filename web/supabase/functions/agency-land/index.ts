const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const landResponses: Record<string, { answer: string; references: { title: string; url: string }[] }> = {
  ราคาประเมิน: {
    answer: `**ราคาประเมินที่ดิน - กรมที่ดิน**\n\n**ราคาประเมินที่ดินกรุงเทพมหานคร (รอบปี 2566-2569):**\n\n| เขต | ราคา (บาท/ตร.วา) |\n|---|---|\n| สีลม/สาทร | 700,000 - 1,000,000 |\n| สุขุมวิท | 400,000 - 800,000 |\n| บางรัก | 500,000 - 750,000 |\n| ลาดพร้าว | 80,000 - 200,000 |\n| บางกะปิ | 60,000 - 150,000 |\n\n**วิธีตรวจสอบราคาประเมิน:**\n1. เว็บไซต์ประเมินราคาที่ดิน กรมธนารักษ์\n2. แอป "ราคาประเมิน"\n3. สำนักงานที่ดินจังหวัด/สาขา`,
    references: [
      { title: 'ระบบค้นหาราคาประเมินที่ดิน', url: 'https://www.dol.go.th/land-price' },
      { title: 'ราคาประเมินทุนทรัพย์', url: 'https://www.treasury.go.th/land-appraisal' },
    ],
  },
  โฉนด: {
    answer: `**การตรวจสอบโฉนดที่ดิน**\n\n**ประเภทเอกสารสิทธิ์:**\n- **น.ส.4 จ. (โฉนดที่ดิน)** — กรรมสิทธิ์สมบูรณ์\n- **น.ส.3 ก.** — สิทธิครอบครอง มีระวาง\n- **น.ส.3** — สิทธิครอบครอง ไม่มีระวาง\n- **ส.ค.1** — ใบแจ้งการครอบครอง\n\n**การตรวจสอบ:**\n1. นำเลขโฉนดไปตรวจสอบที่สำนักงานที่ดิน\n2. ค่าธรรมเนียม 20 บาท/แปลง\n3. ตรวจสอบออนไลน์ผ่านระบบ e-LandsSearch`,
    references: [
      { title: 'ระบบตรวจสอบโฉนดที่ดิน', url: 'https://www.dol.go.th/elandssearch' },
    ],
  },
  จดทะเบียน: {
    answer: `**การจดทะเบียนสิทธิและนิติกรรม**\n\n**ค่าธรรมเนียมการโอน:**\n- ค่าจดทะเบียนโอน: 2% ของราคาประเมิน\n- ค่าอากรแสตมป์: 0.5% หรือภาษีธุรกิจเฉพาะ 3.3%\n- ค่าจดจำนอง: 1% ของวงเงินจำนอง (สูงสุด 200,000 บาท)\n\n**เอกสารที่ต้องเตรียม:**\n1. โฉนดที่ดินฉบับจริง\n2. บัตรประชาชน\n3. ทะเบียนบ้าน\n4. สัญญาซื้อขาย\n5. หนังสือยินยอมคู่สมรส (ถ้ามี)`,
    references: [
      { title: 'การจดทะเบียนสิทธิ', url: 'https://www.dol.go.th/registration' },
    ],
  },
};

function findResponse(query: string) {
  const q = query.toLowerCase();
  if (q.includes('ราคาประเมิน') || q.includes('price') || q.includes('ราคา')) return landResponses['ราคาประเมิน'];
  if (q.includes('โฉนด') || q.includes('เอกสารสิทธิ์') || q.includes('title deed')) return landResponses['โฉนด'];
  if (q.includes('จดทะเบียน') || q.includes('โอน') || q.includes('จำนอง')) return landResponses['จดทะเบียน'];
  return landResponses['ราคาประเมิน'];
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();
  const { query } = await req.json();

  await new Promise((r) => setTimeout(r, 400 + Math.random() * 350));

  const result = findResponse(query);

  return new Response(
    JSON.stringify({
      success: true,
      agency: 'land',
      agencyName: 'กรมที่ดิน',
      data: {
        answer: result.answer,
        references: result.references,
        confidence: 0.88 + Math.random() * 0.10,
      },
      responseTime: Date.now() - start,
    }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
