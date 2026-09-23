const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const revenueResponses: Record<string, { answer: string; references: { title: string; url: string }[] }> = {
  ลดหย่อน: {
    answer: `**สิทธิลดหย่อนภาษีเงินได้บุคคลธรรมดา ปี 2568**\n\n**ค่าลดหย่อนส่วนตัวและครอบครัว:**\n- ผู้มีเงินได้ 60,000 บาท\n- คู่สมรส 60,000 บาท\n- บุตร คนละ 30,000 บาท (บุตรคนที่ 2 เป็นต้นไปเกิดตั้งแต่ปี 2561 ลดหย่อนได้ 60,000 บาท)\n\n**ค่าลดหย่อนกลุ่มประกัน:**\n- ประกันสังคม ตามจริงไม่เกิน 9,000 บาท\n- ประกันชีวิต ไม่เกิน 100,000 บาท\n- ประกันสุขภาพ ไม่เกิน 25,000 บาท\n\n**ค่าลดหย่อนเพื่อการออม:**\n- กองทุนสำรองเลี้ยงชีพ / กบข. ตามจริง\n- RMF ไม่เกิน 30% ของเงินได้\n- SSF ไม่เกิน 30% ของเงินได้\n- รวม RMF + SSF + กองทุนฯ ไม่เกิน 500,000 บาท`,
    references: [
      { title: 'ค่าลดหย่อนภาษี 2568', url: 'https://www.rd.go.th/tax-deduction' },
      { title: 'คู่มือการยื่นแบบ ภ.ง.ด.90/91', url: 'https://www.rd.go.th/efiling' },
    ],
  },
  ภาษี: {
    answer: `**อัตราภาษีเงินได้บุคคลธรรมดา**\n\n| เงินได้สุทธิ (บาท) | อัตราภาษี |\n|---|---|\n| 0 - 150,000 | ยกเว้น |\n| 150,001 - 300,000 | 5% |\n| 300,001 - 500,000 | 10% |\n| 500,001 - 750,000 | 15% |\n| 750,001 - 1,000,000 | 20% |\n| 1,000,001 - 2,000,000 | 25% |\n| 2,000,001 - 5,000,000 | 30% |\n| 5,000,001 ขึ้นไป | 35% |\n\n**กำหนดยื่นแบบ:** ภายในวันที่ 31 มีนาคม ของปีถัดไป (ยื่นออนไลน์ขยายถึง 8 เมษายน)`,
    references: [
      { title: 'อัตราภาษีเงินได้บุคคลธรรมดา', url: 'https://www.rd.go.th/tax-rate' },
    ],
  },
  vat: {
    answer: `**ภาษีมูลค่าเพิ่ม (VAT)**\n\n- อัตราปัจจุบัน: **7%** (รวมภาษีท้องถิ่น)\n- ผู้ประกอบการที่มีรายได้เกิน 1.8 ล้านบาท/ปี ต้องจดทะเบียน VAT\n- ยื่นแบบ ภ.พ.30 ภายในวันที่ 15 ของเดือนถัดไป\n\n**สินค้า/บริการที่ได้รับยกเว้น:**\n- สินค้าเกษตรที่ยังไม่แปรรูป\n- หนังสือพิมพ์ นิตยสาร ตำราเรียน\n- บริการการศึกษา\n- บริการรักษาพยาบาล`,
    references: [
      { title: 'ภาษีมูลค่าเพิ่ม', url: 'https://www.rd.go.th/vat' },
    ],
  },
};

function findResponse(query: string) {
  const q = query.toLowerCase();
  if (q.includes('ลดหย่อน') || q.includes('deduction')) return revenueResponses['ลดหย่อน'];
  if (q.includes('vat') || q.includes('มูลค่าเพิ่ม')) return revenueResponses['vat'];
  return revenueResponses['ภาษี'];
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();
  const { query } = await req.json();

  await new Promise((r) => setTimeout(r, 300 + Math.random() * 400));

  const result = findResponse(query);

  return new Response(
    JSON.stringify({
      success: true,
      agency: 'revenue',
      agencyName: 'กรมสรรพากร',
      data: {
        answer: result.answer,
        references: result.references,
        confidence: 0.90 + Math.random() * 0.09,
      },
      responseTime: Date.now() - start,
    }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
