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
    const body = await req.json();
    const { title, preview, agencies, status, responseTime, messages } = body;

    // Insert conversation
    const { data: conv, error: convError } = await supabase
      .from('conversations')
      .insert({
        title: title || 'สนทนาใหม่',
        preview: preview || '',
        agencies: agencies || [],
        status: status || 'success',
        message_count: messages?.length || 0,
        response_time: responseTime || null,
      })
      .select('id')
      .single();

    if (convError) throw convError;

    // Insert messages
    if (messages && messages.length > 0) {
      const rows = messages.map((m: any) => ({
        id: m.id || undefined,
        conversation_id: conv.id,
        role: m.role,
        content: m.content,
        agent_steps: m.agentSteps || null,
        sources: m.sources || null,
        rating: m.rating || null,
      }));

      const { error: msgError } = await supabase.from('messages').insert(rows);
      if (msgError) throw msgError;
    }

    return new Response(
      JSON.stringify({ success: true, conversationId: conv.id }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err: any) {
    return new Response(
      JSON.stringify({ success: false, error: err.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
