const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const dopaResponses: Record<string, { answer: string; references: { title: string; url: string }[] }> = {
  บัตรประชาชน: {
    answer: `**ขั้นตอนการทำบัตรประจำตัวประชาชน**\n\n**กรณีทำบัตรใหม่ (บัตรหาย/ชำรุด):**\n1. ไปที่สำนักงานเขต/ที่ว่าการอำเภอ\n2. แจ้งความกรณีบัตรหาย (ไม่จำเป็นต้องมีใบแจ้งความแล้ว)\n3. ยื่นคำร้องขอทำบัตรใหม่\n4. ถ่ายรูปและพิมพ์ลายนิ้วมือ\n5. รอรับบัตรใหม่ประมาณ 15-30 นาที\n\n**เอกสารที่ต้องใช้:**\n- สำเนาทะเบียนบ้าน\n- เอกสารที่มีรูปถ่าย (ถ้ามี) เช่น ใบขับขี่ พาสปอร์ต\n\n**ค่าธรรมเนียม:**\n- บัตรหาย/ชำรุด: 100 บาท\n- บัตรหมดอายุ: ไม่เสียค่าธรรมเนียม\n- ทำบัตรครั้งแรก: ไม่เสียค่าธรรมเนียม`,
    references: [
      { title: 'บริการบัตรประจำตัวประชาชน', url: 'https://www.dopa.go.th/service/idcard' },
      { title: 'คู่มือประชาชน - บัตรประชาชน', url: 'https://www.dopa.go.th/citizen-guide' },
    ],
  },
  ทะเบียนบ้าน: {
    answer: `**งานทะเบียนบ้าน**\n\n**การแจ้งย้ายที่อยู่:**\n1. แจ้งย้ายออกจากทะเบียนบ้านเดิม\n2. แจ้งย้ายเข้าทะเบียนบ้านใหม่ภายใน 15 วัน\n\n**การขอสำเนาทะเบียนบ้าน:**\n- ยื่นคำร้องที่สำนักงานเขต/อำเภอ\n- ค่าธรรมเนียม 20 บาท/ฉบับ\n\n**การแจ้งเกิด:**\n- แจ้งภายใน 15 วันนับจากวันเกิด\n- ที่สำนักงานเขต/อำเภอท้องที่ที่เกิด`,
    references: [
      { title: 'งานทะเบียนราษฎร์', url: 'https://www.dopa.go.th/service/registration' },
    ],
  },
  เปลี่ยนชื่อ: {
    answer: `**การเปลี่ยนชื่อตัว-ชื่อสกุล**\n\n**การเปลี่ยนชื่อตัว:**\n1. ยื่นคำร้อง ช.1 ที่สำนักงานเขต/อำเภอ\n2. ค่าธรรมเนียม 50 บาท\n3. ดำเนินการได้ทันที\n\n**การเปลี่ยนชื่อสกุล:**\n1. ยื่นคำร้อง ช.6 ที่สำนักงานเขต/อำเภอ\n2. ตรวจสอบชื่อสกุลซ้ำ\n3. ค่าธรรมเนียม 100 บาท\n4. ใช้เวลาประมาณ 30 วัน`,
    references: [
      { title: 'การเปลี่ยนชื่อ', url: 'https://www.dopa.go.th/service/name-change' },
    ],
  },
};

function findResponse(query: string) {
  const q = query.toLowerCase();
  if (q.includes('บัตรประชาชน') || q.includes('id card') || q.includes('บัตร')) return dopaResponses['บัตรประชาชน'];
  if (q.includes('ทะเบียนบ้าน') || q.includes('ย้าย') || q.includes('เกิด')) return dopaResponses['ทะเบียนบ้าน'];
  if (q.includes('เปลี่ยนชื่อ') || q.includes('ชื่อสกุล') || q.includes('name')) return dopaResponses['เปลี่ยนชื่อ'];
  return dopaResponses['บัตรประชาชน'];
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();
  const { query } = await req.json();

  await new Promise((r) => setTimeout(r, 350 + Math.random() * 300));

  const result = findResponse(query);

  return new Response(
    JSON.stringify({
      success: true,
      agency: 'dopa',
      agencyName: 'กรมการปกครอง',
      data: {
        answer: result.answer,
        references: result.references,
        confidence: 0.91 + Math.random() * 0.08,
      },
      responseTime: Date.now() - start,
    }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
