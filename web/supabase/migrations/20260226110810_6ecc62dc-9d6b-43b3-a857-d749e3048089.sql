
CREATE TABLE public.connection_logs (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  agency_id uuid NOT NULL REFERENCES public.agencies(id) ON DELETE CASCADE,
  action text NOT NULL DEFAULT 'call',
  connection_type text NOT NULL DEFAULT 'API',
  status text NOT NULL DEFAULT 'success',
  latency_ms integer NOT NULL DEFAULT 0,
  detail text NOT NULL DEFAULT '',
  created_at timestamp with time zone NOT NULL DEFAULT now()
);

ALTER TABLE public.connection_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read connection_logs" ON public.connection_logs FOR SELECT USING (true);
CREATE POLICY "Public insert connection_logs" ON public.connection_logs FOR INSERT WITH CHECK (true);

ALTER PUBLICATION supabase_realtime ADD TABLE public.connection_logs;

INSERT INTO public.connection_logs (agency_id, action, connection_type, status, latency_ms, detail, created_at)
SELECT a.id, v.act, a.connection_type, v.st, v.lat, v.det, v.ts
FROM public.agencies a
CROSS JOIN (VALUES
  ('call'::text, 'success'::text, 120, 'Handshake สำเร็จ'::text, now() - interval '1 hour'),
  ('call'::text, 'success'::text, 95, 'ดึงข้อมูลสำเร็จ'::text, now() - interval '2 hours'),
  ('test'::text, 'success'::text, 150, 'ทดสอบการเชื่อมต่อ'::text, now() - interval '3 hours'),
  ('call'::text, 'success'::text, 88, 'สืบค้นข้อมูล'::text, now() - interval '5 hours'),
  ('call'::text, 'error'::text, 5000, 'Connection timeout'::text, now() - interval '8 hours'),
  ('call'::text, 'success'::text, 110, 'ดึงข้อมูลสำเร็จ'::text, now() - interval '12 hours'),
  ('test'::text, 'success'::text, 200, 'Health check ผ่าน'::text, now() - interval '1 day'),
  ('call'::text, 'success'::text, 130, 'Query completed'::text, now() - interval '1 day 2 hours'),
  ('call'::text, 'success'::text, 75, 'Cache hit'::text, now() - interval '2 days'),
  ('call'::text, 'error'::text, 3000, 'Service unavailable'::text, now() - interval '3 days')
) AS v(act, st, lat, det, ts);
