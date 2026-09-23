const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response(null, { headers: corsHeaders });

  try {
    const now = new Date();
    const minute = Math.floor(now.getTime() / 60000);
    const rand = seeded(minute);

    const baseAgencies = [
      { id: 'fda', name: 'อย.', shortName: 'FDA', baseUptime: 99.5, baseLatency: 245 },
      { id: 'revenue', name: 'กรมสรรพากร', shortName: 'Revenue', baseUptime: 99.8, baseLatency: 180 },
      { id: 'dopa', name: 'กรมการปกครอง', shortName: 'DOPA', baseUptime: 98.2, baseLatency: 420 },
      { id: 'land', name: 'กรมที่ดิน', shortName: 'Land', baseUptime: 97.5, baseLatency: 510 },
    ];

    // Real-time current status
    const agencies = baseAgencies.map(a => {
      const r = seeded(minute + a.id.charCodeAt(0))();
      const currentLatency = Math.max(50, a.baseLatency + Math.floor((r - 0.5) * 200));
      const isUp = r > 0.02; // 2% chance down
      const uptime = parseFloat((a.baseUptime + (r - 0.5) * 0.4).toFixed(2));
      const errorRate = parseFloat((Math.max(0, (100 - uptime)) + r * 0.3).toFixed(2));
      const requestsPerMin = Math.floor(120 + r * 80);

      let status: 'healthy' | 'degraded' | 'down' = 'healthy';
      if (!isUp) status = 'down';
      else if (currentLatency > a.baseLatency * 1.5 || errorRate > 1) status = 'degraded';

      return {
        id: a.id,
        name: a.name,
        shortName: a.shortName,
        status,
        uptime,
        currentLatency,
        avgLatency: a.baseLatency,
        errorRate,
        requestsPerMin,
        lastCheckedAt: now.toISOString(),
      };
    });

    // Historical chart - last 24 hours, 1 point per hour
    const hours = 24;
    const historical = Array.from({ length: hours }, (_, i) => {
      const hourOffset = hours - 1 - i;
      const t = new Date(now.getTime() - hourOffset * 3600000);
      const point: any = { time: `${String(t.getHours()).padStart(2, '0')}:00` };
      baseAgencies.forEach(a => {
        const r = seeded(minute - hourOffset * 60 + a.id.charCodeAt(0))();
        point[`${a.id}_latency`] = Math.max(50, Math.floor(a.baseLatency + (r - 0.5) * 150));
        point[`${a.id}_uptime`] = parseFloat((a.baseUptime + (r - 0.5) * 0.5).toFixed(2));
      });
      return point;
    });

    // Incidents in last 24h
    const incidents = [
      { agency: 'กรมที่ดิน', type: 'high_latency', severity: 'warning', message: 'Latency เกิน 800ms ต่อเนื่อง 5 นาที', occurredAt: new Date(now.getTime() - 2 * 3600000).toISOString(), resolvedAt: new Date(now.getTime() - 1.5 * 3600000).toISOString() },
      { agency: 'กรมการปกครอง', type: 'error_spike', severity: 'critical', message: 'Error rate กระโดดเป็น 3.2%', occurredAt: new Date(now.getTime() - 8 * 3600000).toISOString(), resolvedAt: new Date(now.getTime() - 7.5 * 3600000).toISOString() },
      { agency: 'อย.', type: 'rate_limit', severity: 'info', message: 'ใกล้แตะ rate limit (85% ของ quota)', occurredAt: new Date(now.getTime() - 14 * 3600000).toISOString(), resolvedAt: new Date(now.getTime() - 13 * 3600000).toISOString() },
    ];

    // SLA compliance summary
    const slaTarget = 99.0;
    const slaCompliance = agencies.map(a => ({
      agency: a.shortName,
      uptime: a.uptime,
      target: slaTarget,
      met: a.uptime >= slaTarget,
    }));

    return new Response(
      JSON.stringify({
        success: true,
        data: {
          agencies,
          historical,
          incidents,
          slaCompliance,
          generatedAt: now.toISOString(),
        },
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (e) {
    console.error('agency-health error:', e);
    return new Response(
      JSON.stringify({ success: false, error: e instanceof Error ? e.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});