const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-supabase-client-platform, x-supabase-client-platform-version, x-supabase-client-runtime, x-supabase-client-runtime-version',
};

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { specText } = await req.json();
    if (!specText || typeof specText !== 'string') {
      return json({ error: 'specText is required' }, 400);
    }

    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');
    if (!LOVABLE_API_KEY) {
      return json({ error: 'LOVABLE_API_KEY not configured' }, 500);
    }

    const response = await fetch('https://ai.gateway.lovable.dev/v1/chat/completions', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${LOVABLE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'google/gemini-3-flash-preview',
        messages: [
          {
            role: 'system',
            content: 'You are an API specification parser. Extract structured information from OpenAPI/Swagger specs including response schemas.',
          },
          {
            role: 'user',
            content: `Parse this API specification and extract the details including response field schemas:\n\n${specText.substring(0, 30000)}`,
          },
        ],
        tools: [
          {
            type: 'function',
            function: {
              name: 'extract_api_spec',
              description: 'Extract structured API specification details including response schemas',
              parameters: {
                type: 'object',
                properties: {
                  auth_method: {
                    type: 'string',
                    enum: ['api_key', 'oauth2', 'basic_auth', 'none'],
                    description: 'Authentication method used by the API',
                  },
                  auth_header: {
                    type: 'string',
                    description: 'Authentication header name, e.g. X-API-Key, Authorization',
                  },
                  base_path: {
                    type: 'string',
                    description: 'Base path prefix for all endpoints, e.g. /api/v1',
                  },
                  request_format: {
                    type: 'string',
                    enum: ['json', 'xml'],
                    description: 'Default request/response format',
                  },
                  endpoints: {
                    type: 'array',
                    items: {
                      type: 'object',
                      properties: {
                        method: { type: 'string', enum: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] },
                        path: { type: 'string' },
                        description: { type: 'string' },
                      },
                      required: ['method', 'path', 'description'],
                      additionalProperties: false,
                    },
                  },
                  response_schema: {
                    type: 'array',
                    description: 'Common response fields found across endpoint responses',
                    items: {
                      type: 'object',
                      properties: {
                        field: { type: 'string', description: 'Field name or dot-notation path e.g. data.items[].name' },
                        type: { type: 'string', description: 'Data type: string, number, boolean, array, object, date' },
                        description: { type: 'string', description: 'What this field contains' },
                        example: { type: 'string', description: 'Example value' },
                      },
                      required: ['field', 'type', 'description'],
                      additionalProperties: false,
                    },
                  },
                },
                required: ['auth_method', 'auth_header', 'base_path', 'request_format', 'endpoints', 'response_schema'],
                additionalProperties: false,
              },
            },
          },
        ],
        tool_choice: { type: 'function', function: { name: 'extract_api_spec' } },
      }),
    });

    if (!response.ok) {
      if (response.status === 429) {
        return json({ error: 'Rate limit exceeded, please try again later.' }, 429);
      }
      if (response.status === 402) {
        return json({ error: 'Payment required.' }, 402);
      }
      const t = await response.text();
      console.error('AI gateway error:', response.status, t);
      return json({ error: 'AI gateway error' }, 500);
    }

    const data = await response.json();
    const toolCall = data.choices?.[0]?.message?.tool_calls?.[0];

    if (!toolCall?.function?.arguments) {
      return json({ error: 'Failed to parse specification' }, 500);
    }

    const parsed = JSON.parse(toolCall.function.arguments);
    return json({ success: true, data: parsed });
  } catch (err) {
    console.error('parse-api-spec error:', err);
    return json({ error: err.message }, 500);
  }
});

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, 'Content-Type': 'application/json' },
  });
}
