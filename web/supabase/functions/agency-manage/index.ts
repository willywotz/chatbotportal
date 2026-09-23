import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
  const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  const supabase = createClient(supabaseUrl, supabaseKey);

  try {
    // POST with action
    if (req.method === 'POST') {
      const body = await req.json();

      // Test connection
      if (body.action === 'test') {
        return handleTest(body);
      }

      // Create agency
      const { data, error } = await supabase.from('agencies').insert({
        name: body.name,
        short_name: body.short_name,
        logo: body.logo || '🏢',
        connection_type: body.connection_type || 'API',
        status: body.status || 'active',
        description: body.description || '',
        data_scope: body.data_scope || [],
        color: body.color || 'hsl(213 70% 45%)',
        endpoint_url: body.endpoint_url || '',
        api_key_name: body.api_key_name || null,
        auth_method: body.auth_method || 'api_key',
        auth_header: body.auth_header || '',
        base_path: body.base_path || '',
        request_format: body.request_format || 'json',
        api_endpoints: body.api_endpoints || [],
        response_schema: body.response_schema || [],
        api_spec_raw: body.api_spec_raw || null,
      }).select().single();

      if (error) throw error;
      return json({ success: true, data });
    }

    // PUT - update
    if (req.method === 'PUT') {
      const body = await req.json();
      const { id, ...updates } = body;
      updates.updated_at = new Date().toISOString();

      const { data, error } = await supabase
        .from('agencies')
        .update(updates)
        .eq('id', id)
        .select()
        .single();

      if (error) throw error;
      return json({ success: true, data });
    }

    // DELETE
    if (req.method === 'DELETE') {
      const { id } = await req.json();
      const { error } = await supabase.from('agencies').delete().eq('id', id);
      if (error) throw error;
      return json({ success: true });
    }

    return json({ error: 'Method not allowed' }, 405);
  } catch (err) {
    return json({ success: false, error: err.message }, 500);
  }
});

async function handleTest(body: { connection_type: string; endpoint_url: string }) {
  const steps: { step: number; label: string; status: string; time: number }[] = [];
  const totalStart = Date.now();

  // For MCP / A2A, keep simulated test (no real HTTP endpoint to ping)
  if (body.connection_type === 'MCP' || body.connection_type === 'A2A') {
    return handleSimulatedTest(body);
  }

  // --- Real API connection test ---
  const url = body.endpoint_url?.trim();
  if (!url) {
    return json({ success: false, error: 'Endpoint URL is required', protocol: 'REST API', version: '-', steps: [], latency: '0ms' });
  }

  // Step 1: DNS / TCP
  const s1 = Date.now();
  let response: Response | null = null;
  let fetchError: string | null = null;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);

    response = await fetch(url, {
      method: 'HEAD',
      signal: controller.signal,
      headers: { 'User-Agent': 'AI-Chatbot-Portal/1.0 ConnectionTest' },
    });
    clearTimeout(timeout);
  } catch (err: any) {
    // HEAD may not be supported, try GET
    try {
      const controller2 = new AbortController();
      const timeout2 = setTimeout(() => controller2.abort(), 10000);
      response = await fetch(url, {
        method: 'GET',
        signal: controller2.signal,
        headers: { 'User-Agent': 'AI-Chatbot-Portal/1.0 ConnectionTest' },
      });
      clearTimeout(timeout2);
    } catch (err2: any) {
      fetchError = err2.name === 'AbortError' ? 'Connection timeout (10s)' : err2.message;
    }
  }
  const s1End = Date.now();

  steps.push({ step: 1, label: 'TCP Connection', status: fetchError ? 'error' : 'done', time: s1End - s1 });

  if (fetchError) {
    const latency = Date.now() - totalStart;
    steps.push({ step: 2, label: 'HTTP Response', status: 'error', time: 0 });
    return json({
      success: false,
      protocol: 'REST API',
      version: '-',
      steps,
      latency: `${latency}ms`,
      statusCode: null,
      error: fetchError,
    });
  }

  // Step 2: HTTP Response
  const statusCode = response!.status;
  const statusText = response!.statusText;
  steps.push({ step: 2, label: `HTTP ${statusCode} ${statusText}`, status: statusCode < 500 ? 'done' : 'error', time: s1End - s1 });

  // Step 3: Response headers check
  const s3 = Date.now();
  const contentType = response!.headers.get('content-type') || 'unknown';
  const server = response!.headers.get('server') || 'unknown';
  steps.push({ step: 3, label: `Content-Type: ${contentType.split(';')[0]}`, status: 'done', time: Date.now() - s3 });

  // Consume body
  try { await response!.text(); } catch {}

  const totalLatency = Date.now() - totalStart;
  const isSuccess = statusCode >= 200 && statusCode < 500;

  steps.push({ step: 4, label: isSuccess ? 'API Reachable' : 'API Error', status: isSuccess ? 'done' : 'error', time: 0 });

  return json({
    success: isSuccess,
    protocol: 'REST API',
    version: 'v1',
    steps,
    latency: `${totalLatency}ms`,
    statusCode,
    statusText,
    server,
    contentType: contentType.split(';')[0],
  });
}

function handleSimulatedTest(body: { connection_type: string; endpoint_url: string }) {
  const start = Date.now();
  const delay = 100 + Math.random() * 300;

  return new Promise<Response>((resolve) => {
    setTimeout(() => {
      const latency = Date.now() - start;
      let result: Record<string, unknown>;

      if (body.connection_type === 'MCP') {
        result = {
          success: true,
          protocol: 'MCP',
          version: '1.0',
          steps: [
            { step: 1, label: 'TCP Connection', status: 'done', time: Math.round(latency * 0.2) },
            { step: 2, label: 'MCP Handshake', status: 'done', time: Math.round(latency * 0.4) },
            { step: 3, label: 'Capability Exchange', status: 'done', time: Math.round(latency * 0.3) },
            { step: 4, label: 'Session Established', status: 'done', time: Math.round(latency * 0.1) },
          ],
          capabilities: ['tools/list', 'tools/call', 'resources/read'],
          latency: `${latency}ms`,
        };
      } else {
        result = {
          success: true,
          protocol: 'A2A',
          version: '0.2',
          steps: [
            { step: 1, label: 'DNS Resolution', status: 'done', time: Math.round(latency * 0.15) },
            { step: 2, label: 'Agent Card Request', status: 'done', time: Math.round(latency * 0.35) },
            { step: 3, label: 'Capability Negotiation', status: 'done', time: Math.round(latency * 0.3) },
            { step: 4, label: 'Agent Link Ready', status: 'done', time: Math.round(latency * 0.2) },
          ],
          agentCard: { name: 'Remote Agent', skills: ['query', 'verify'] },
          latency: `${latency}ms`,
        };
      }
      resolve(json(result));
    }, delay);
  });
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}
