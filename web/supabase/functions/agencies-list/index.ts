import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const start = Date.now();
  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  const supabase = createClient(supabaseUrl, supabaseKey);

  const { data, error } = await supabase
    .from('agencies')
    .select('*')
    .eq('status', 'active')
    .order('created_at', { ascending: true });

  if (error) {
    return new Response(
      JSON.stringify({ success: false, error: error.message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }

  // Map to the format the ai-chat function expects
  const agencies = (data || []).map((a: any) => ({
    id: a.id,
    name: a.name,
    shortName: a.short_name,
    logo: a.logo,
    connectionType: a.connection_type,
    status: a.status,
    description: a.description,
    dataScope: a.data_scope,
    totalCalls: a.total_calls,
    color: a.color,
    lastPing: Date.now() - Math.floor(Math.random() * 5000),
    uptime: parseFloat((99.0 + Math.random() * 0.9).toFixed(2)),
  }));

  return new Response(
    JSON.stringify({ success: true, data: agencies, responseTime: Date.now() - start }),
    { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
  );
});
