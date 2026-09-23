import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  const supabase = createClient(supabaseUrl, supabaseKey);

  try {
    // Get all rated messages with their conversations
    const { data: ratedMessages, error } = await supabase
      .from('messages')
      .select('id, rating, feedback_text, content, created_at, conversation_id')
      .not('rating', 'is', null)
      .order('created_at', { ascending: false });

    if (error) throw error;

    const messages = ratedMessages || [];
    const upCount = messages.filter((m: any) => m.rating === 'up').length;
    const downCount = messages.filter((m: any) => m.rating === 'down').length;
    const totalRatings = upCount + downCount;
    const satisfactionRate = totalRatings > 0 ? Math.round((upCount / totalRatings) * 100) : 0;

    // Daily trend (last 14 days)
    const dailyMap: Record<string, { up: number; down: number }> = {};
    const now = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().split('T')[0];
      dailyMap[key] = { up: 0, down: 0 };
    }

    for (const m of messages) {
      const day = (m as any).created_at?.split('T')[0];
      if (dailyMap[day]) {
        if ((m as any).rating === 'up') dailyMap[day].up++;
        else if ((m as any).rating === 'down') dailyMap[day].down++;
      }
    }

    const dailyTrend = Object.entries(dailyMap).map(([date, counts]) => ({
      date: date.slice(5), // MM-DD
      up: counts.up,
      down: counts.down,
      rate: counts.up + counts.down > 0 ? Math.round((counts.up / (counts.up + counts.down)) * 100) : 0,
    }));

    // Low-rated questions: get the user message before each down-rated assistant message
    const downRated = messages.filter((m: any) => m.rating === 'down').slice(0, 10);
    const lowRatedQuestions: any[] = [];

    for (const dr of downRated) {
      // Find the user message in same conversation just before this assistant message
      const { data: convMsgs } = await supabase
        .from('messages')
        .select('content, role, created_at')
        .eq('conversation_id', (dr as any).conversation_id)
        .eq('role', 'user')
        .order('created_at', { ascending: false })
        .limit(1);

      // Get conversation agencies
      const { data: conv } = await supabase
        .from('conversations')
        .select('agencies')
        .eq('id', (dr as any).conversation_id)
        .single();

      lowRatedQuestions.push({
        content: convMsgs?.[0]?.content || 'ไม่ทราบคำถาม',
        feedback_text: (dr as any).feedback_text,
        agency: (conv as any)?.agencies?.join(', ') || '-',
        created_at: (dr as any).created_at,
      });
    }

    // Agency breakdown from conversations
    const agencyMap: Record<string, { up: number; down: number }> = {};
    for (const m of messages) {
      const { data: conv } = await supabase
        .from('conversations')
        .select('agencies')
        .eq('id', (m as any).conversation_id)
        .single();

      const agencies = (conv as any)?.agencies || [];
      for (const ag of agencies) {
        if (!agencyMap[ag]) agencyMap[ag] = { up: 0, down: 0 };
        if ((m as any).rating === 'up') agencyMap[ag].up++;
        else agencyMap[ag].down++;
      }
    }

    const agencyBreakdown = Object.entries(agencyMap).map(([agency, counts]) => ({
      agency,
      up: counts.up,
      down: counts.down,
      rate: counts.up + counts.down > 0 ? Math.round((counts.up / (counts.up + counts.down)) * 100) : 0,
    })).sort((a, b) => b.up + b.down - (a.up + a.down));

    return new Response(
      JSON.stringify({
        totalRatings,
        upCount,
        downCount,
        satisfactionRate,
        dailyTrend,
        lowRatedQuestions,
        agencyBreakdown,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err: any) {
    return new Response(
      JSON.stringify({ error: err.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
