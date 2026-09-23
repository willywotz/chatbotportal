import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

interface AgencyResult {
  success: boolean;
  agency: string;
  agencyName: string;
  data: {
    answer: string;
    references: { title: string; url: string }[];
    confidence: number;
  };
  responseTime: number;
}

interface ResponseField {
  field: string;
  type: string;
  description: string;
  example?: string;
}

interface AgencyConfig {
  id: string;
  short_name: string;
  name: string;
  logo: string;
  response_schema: ResponseField[] | null;
  api_endpoints: any[] | null;
  connection_type: string;
}

// Keyword-based agency routing
function detectAgencies(query: string): string[] {
  const q = query.toLowerCase();
  const matched: string[] = [];

  if (q.includes('ยา') || q.includes('อาหาร') || q.includes('เครื่องสำอาง') || q.includes('อย.') || q.includes('พาราเซตามอล') || q.includes('นำเข้า') || q.includes('ผลิตภัณฑ์สุขภาพ')) {
    matched.push('fda');
  }
  if (q.includes('ภาษี') || q.includes('ลดหย่อน') || q.includes('สรรพากร') || q.includes('vat') || q.includes('ยื่นแบบ') || q.includes('เงินได้')) {
    matched.push('revenue');
  }
  if (q.includes('บัตรประชาชน') || q.includes('ทะเบียนราษฎร์') || q.includes('ทะเบียนบ้าน') || q.includes('ปกครอง') || q.includes('เปลี่ยนชื่อ') || q.includes('แจ้งเกิด')) {
    matched.push('dopa');
  }
  if (q.includes('ที่ดิน') || q.includes('โฉนด') || q.includes('ราคาประเมิน') || q.includes('จดทะเบียน') || q.includes('รังวัด') || q.includes('โอนที่ดิน')) {
    matched.push('land');
  }

  if (matched.length === 0) matched.push('fda');
  return matched;
}

const agencyFunctionMap: Record<string, string> = {
  fda: 'agency-fda',
  revenue: 'agency-revenue',
  dopa: 'agency-dopa',
  land: 'agency-land',
};

const agencyNameMap: Record<string, string> = {
  fda: 'สำนักงาน อย.',
  revenue: 'กรมสรรพากร',
  dopa: 'กรมการปกครอง',
  land: 'กรมที่ดิน',
};

const agencyIconMap: Record<string, string> = {
  fda: '🏥',
  revenue: '💰',
  dopa: '🏛️',
  land: '🗺️',
};

// Short name → agency key mapping for DB lookup
const shortNameToKey: Record<string, string> = {
  'อย.': 'fda',
  'สรรพากร': 'revenue',
  'ปกครอง': 'dopa',
  'ที่ดิน': 'land',
};

const AI_GATEWAY_URL = 'https://ai.gateway.lovable.dev/v1/chat/completions';

/**
 * Build a schema guide string for the LLM prompt from agency response_schema
 */
function buildSchemaGuide(agencyConfigs: Map<string, AgencyConfig>, targetAgencies: string[]): string {
  const sections: string[] = [];

  for (const agencyId of targetAgencies) {
    // Find matching config by short_name pattern
    let config: AgencyConfig | undefined;
    for (const [, c] of agencyConfigs) {
      const sn = c.short_name.replace('.', '').toLowerCase();
      if (
        (agencyId === 'fda' && (sn.includes('อย') || c.name.includes('อาหาร'))) ||
        (agencyId === 'revenue' && (sn.includes('สรรพากร') || c.name.includes('สรรพากร'))) ||
        (agencyId === 'dopa' && (sn.includes('ปกครอง') || c.name.includes('ปกครอง'))) ||
        (agencyId === 'land' && (sn.includes('ที่ดิน') || c.name.includes('ที่ดิน')))
      ) {
        config = c;
        break;
      }
    }

    if (!config?.response_schema?.length) continue;

    const fields = config.response_schema.map((f: ResponseField) => {
      let line = `  - **${f.field}** (${f.type}): ${f.description}`;
      if (f.example) line += ` — ตัวอย่าง: ${f.example}`;
      return line;
    }).join('\n');

    sections.push(`#### ${config.name} (${config.short_name})\nResponse fields ที่สำคัญ:\n${fields}`);
  }

  return sections.length > 0
    ? `\n\n## Schema Reference สำหรับ Parse ข้อมูล\nใช้ข้อมูล schema ด้านล่างเพื่อระบุและจัดรูปแบบข้อมูลในคำตอบให้ถูกต้อง:\n\n${sections.join('\n\n')}`
    : '';
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();

  try {
    const { query } = await req.json();
    if (!query || typeof query !== 'string') {
      return new Response(
        JSON.stringify({ success: false, error: 'Missing query parameter' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // Step 1: Detect relevant agencies
    const targetAgencies = detectAgencies(query);

    // Step 1.5: Fetch agency configs (response_schema) from DB
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabaseKey = Deno.env.get('SUPABASE_ANON_KEY')!;

    const agencyConfigs = new Map<string, AgencyConfig>();
    try {
      const supabase = createClient(supabaseUrl, supabaseServiceKey);
      const { data: agencies } = await supabase
        .from('agencies')
        .select('id, short_name, name, logo, response_schema, api_endpoints, connection_type')
        .eq('status', 'active');

      if (agencies) {
        for (const a of agencies) {
          agencyConfigs.set(a.id, a as AgencyConfig);
        }
      }
    } catch (dbErr) {
      console.error('Failed to fetch agency configs:', dbErr);
      // Continue without schema — graceful degradation
    }

    // Step 2: Build agent steps
    const agentSteps = [
      { icon: '🔍', label: 'กำลังวิเคราะห์คำถาม...', status: 'done' },
      { icon: '📋', label: `วางแผนการสืบค้น → เลือกหน่วยงาน: ${targetAgencies.map(a => agencyNameMap[a]).join(', ')}`, status: 'done' },
    ];

    // Step 3: Call agency functions in parallel
    const agencyPromises = targetAgencies.map(async (agencyId) => {
      const fnName = agencyFunctionMap[agencyId];
      agentSteps.push({
        icon: '🔗',
        label: `กำลังสืบค้นจาก ${agencyNameMap[agencyId]} ...`,
        status: 'done',
      });

      try {
        const res = await fetch(`${supabaseUrl}/functions/v1/${fnName}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${supabaseKey}`,
          },
          body: JSON.stringify({ query }),
        });
        return (await res.json()) as AgencyResult;
      } catch {
        return null;
      }
    });

    const results = (await Promise.all(agencyPromises)).filter(Boolean) as AgencyResult[];

    agentSteps.push(
      { icon: '✅', label: 'รวบรวมและประเมินผลลัพธ์', status: 'done' },
    );

    // Step 4: Synthesize answer using Lovable AI
    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');
    let combinedAnswer: string;

    if (LOVABLE_API_KEY && results.length > 0) {
      agentSteps.push({ icon: '🤖', label: 'AI กำลังสังเคราะห์คำตอบ (พร้อม Schema Guide)...', status: 'done' });

      const agencyContext = results.map((r) =>
        `### ข้อมูลจาก ${r.agencyName}\n${r.data.answer}`
      ).join('\n\n');

      // Build schema guide from DB configs
      const schemaGuide = buildSchemaGuide(agencyConfigs, targetAgencies);

      const systemPrompt = `คุณคือ AI ผู้ช่วยภาครัฐไทย ทำหน้าที่สังเคราะห์ข้อมูลจากหลายหน่วยงานราชการให้เป็นคำตอบที่ชัดเจน ถูกต้อง และเข้าใจง่ายสำหรับประชาชน

กฎ:
- ตอบเป็นภาษาไทยเสมอ
- ใช้ Markdown formatting (หัวข้อ, bullet points, ตัวหนา) ให้อ่านง่าย
- อ้างอิงชื่อหน่วยงานที่เป็นแหล่งข้อมูลในคำตอบ
- หากข้อมูลจากหลายหน่วยงานเกี่ยวข้องกัน ให้เชื่อมโยงและสรุปให้เป็นคำตอบเดียวที่สอดคล้องกัน
- ห้ามเพิ่มข้อมูลที่ไม่มีในแหล่งข้อมูลที่ให้มา
- จบคำตอบด้วยข้อแนะนำเพิ่มเติมหากเหมาะสม
- เมื่อมี Schema Reference ให้ใช้เป็นแนวทางในการระบุและจัดรูปแบบข้อมูลสำคัญ เช่น ตัวเลข วันที่ สถานะ ให้ถูกต้องตาม field type ที่กำหนด
- หาก response มี field ตรงกับ schema ให้แสดงข้อมูลครบถ้วนตาม field ที่ระบุ${schemaGuide}`;

      const userPrompt = `คำถามจากประชาชน: "${query}"

ข้อมูลที่สืบค้นได้จากหน่วยงานราชการ:

${agencyContext}

กรุณาสังเคราะห์ข้อมูลข้างต้นเป็นคำตอบที่ครบถ้วนและเข้าใจง่ายสำหรับประชาชน`;

      try {
        const aiResponse = await fetch(AI_GATEWAY_URL, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${LOVABLE_API_KEY}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            model: 'google/gemini-3-flash-preview',
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: userPrompt },
            ],
          }),
        });

        if (aiResponse.ok) {
          const aiData = await aiResponse.json();
          combinedAnswer = aiData.choices?.[0]?.message?.content || results.map((r) => r.data.answer).join('\n\n---\n\n');
        } else {
          const errText = await aiResponse.text();
          console.error('AI gateway error:', aiResponse.status, errText);
          combinedAnswer = results.map((r) => r.data.answer).join('\n\n---\n\n');
        }
      } catch (aiErr) {
        console.error('AI synthesis error:', aiErr);
        combinedAnswer = results.map((r) => r.data.answer).join('\n\n---\n\n');
      }
    } else {
      combinedAnswer = results.map((r) => r.data.answer).join('\n\n---\n\n');
    }

    agentSteps.push({ icon: '📝', label: 'สังเคราะห์คำตอบเสร็จสิ้น', status: 'done' });

    const allReferences = results.flatMap((r) =>
      r.data.references.map((ref) => ({
        agency: r.agencyName,
        ...ref,
      }))
    );

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          answer: combinedAnswer,
          references: allReferences,
          agentSteps,
          agencies: targetAgencies.map((id) => ({
            id,
            name: agencyNameMap[id],
            icon: agencyIconMap[id],
          })),
          confidence: results.reduce((sum, r) => sum + r.data.confidence, 0) / results.length,
        },
        responseTime: Date.now() - start,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    return new Response(
      JSON.stringify({ success: false, error: String(error) }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
