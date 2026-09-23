const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const fdaResponses: Record<string, { answer: string; references: { title: string; url: string }[] }> = {
  ยา: {
    answer: `**ระบบตรวจสอบทะเบียนยา - สำนักงาน อย.**\n\nยาทุกชนิดที่จำหน่ายในประเทศไทยต้องขึ้นทะเบียนกับ อย. ตาม พ.ร.บ. ยา พ.ศ. 2510\n\n**ประเภทยา:**\n- ยาสามัญประจำบ้าน — ซื้อได้ทั่วไป\n- ยาอันตราย — ต้องซื้อจากร้านขายยาที่มีเภสัชกร\n- ยาควบคุมพิเศษ — ต้องมีใบสั่งแพทย์\n\n**การตรวจสอบ:** สามารถตรวจสอบเลขทะเบียนยาได้ที่เว็บไซต์ อย. หรือแอป "อย. Smart Application"`,
    references: [
      { title: 'ระบบตรวจสอบทะเบียนยา', url: 'https://www.fda.moph.go.th/sites/drug' },
      { title: 'พ.ร.บ. ยา พ.ศ. 2510', url: 'https://www.fda.moph.go.th/sites/drug/law' },
    ],
  },
  อาหาร: {
    answer: `**ระบบตรวจสอบทะเบียนอาหาร - สำนักงาน อย.**\n\nผลิตภัณฑ์อาหารที่จำหน่ายในประเทศไทยต้องได้รับอนุญาตจาก อย.\n\n**เครื่องหมาย อย.:**\n- เลข อย. 13 หลัก แสดงว่าผ่านการตรวจสอบ\n- ตรวจสอบได้ที่เว็บไซต์ อย.\n\n**ประเภทอาหาร:**\n- อาหารควบคุมเฉพาะ\n- อาหารที่กำหนดคุณภาพ\n- อาหารที่ต้องมีฉลาก\n- อาหารทั่วไป`,
    references: [
      { title: 'ตรวจสอบเลข อย.', url: 'https://www.fda.moph.go.th/sites/food' },
    ],
  },
  เครื่องสำอาง: {
    answer: `**ระบบจดแจ้งเครื่องสำอาง - สำนักงาน อย.**\n\nเครื่องสำอางทุกชนิดต้องจดแจ้งกับ อย. ก่อนจำหน่าย\n\n**ขั้นตอน:**\n1. ยื่นจดแจ้งผ่านระบบ e-Submission\n2. ตรวจสอบส่วนประกอบตามประกาศกระทรวง\n3. ได้รับเลขจดแจ้ง 10 หลัก\n\n**สารต้องห้าม:** สารปรอท, ไฮโดรควิโนน, สเตียรอยด์`,
    references: [
      { title: 'ระบบจดแจ้งเครื่องสำอาง', url: 'https://www.fda.moph.go.th/sites/cosmetic' },
    ],
  },
};

function findResponse(query: string) {
  const q = query.toLowerCase();
  if (q.includes('ยา') || q.includes('พาราเซตามอล') || q.includes('drug')) return fdaResponses['ยา'];
  if (q.includes('อาหาร') || q.includes('food') || q.includes('อย.')) return fdaResponses['อาหาร'];
  if (q.includes('เครื่องสำอาง') || q.includes('cosmetic')) return fdaResponses['เครื่องสำอาง'];
  return fdaResponses['ยา']; // default
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();
  const { query } = await req.json();

  // Simulate processing delay
  await new Promise((r) => setTimeout(r, 400 + Math.random() * 300));

  const result = findResponse(query);

  return new Response(
    JSON.stringify({
      success: true,
      agency: 'fda',
      agencyName: 'สำนักงานคณะกรรมการอาหารและยา',
      data: {
        answer: result.answer,
        references: result.references,
        confidence: 0.92 + Math.random() * 0.07,
      },
      responseTime: Date.now() - start,
    }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
