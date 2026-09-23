
-- Create agencies table
CREATE TABLE public.agencies (
  id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  name text NOT NULL,
  short_name text NOT NULL,
  logo text NOT NULL DEFAULT '🏢',
  connection_type text NOT NULL DEFAULT 'API',
  status text NOT NULL DEFAULT 'active',
  description text NOT NULL DEFAULT '',
  data_scope text[] NOT NULL DEFAULT '{}',
  total_calls integer NOT NULL DEFAULT 0,
  color text NOT NULL DEFAULT 'hsl(213 70% 45%)',
  endpoint_url text NOT NULL DEFAULT '',
  api_key_name text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- RLS policies (public access, no auth yet)
ALTER TABLE public.agencies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read agencies" ON public.agencies FOR SELECT USING (true);
CREATE POLICY "Public insert agencies" ON public.agencies FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update agencies" ON public.agencies FOR UPDATE USING (true);
CREATE POLICY "Public delete agencies" ON public.agencies FOR DELETE USING (true);

-- Enable realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.agencies;

-- Seed data
INSERT INTO public.agencies (id, name, short_name, logo, connection_type, status, description, data_scope, total_calls, color, endpoint_url) VALUES
  (gen_random_uuid(), 'สำนักงานคณะกรรมการอาหารและยา', 'อย.', '🏥', 'MCP', 'active', 'ระบบตรวจสอบทะเบียนยา อาหาร เครื่องสำอาง และผลิตภัณฑ์สุขภาพ', ARRAY['ทะเบียนยา','ทะเบียนอาหาร','เครื่องสำอาง','ผลิตภัณฑ์สุขภาพ','การขออนุญาต'], 12450, 'hsl(145 55% 40%)', 'https://api.fda.moph.go.th/mcp'),
  (gen_random_uuid(), 'กรมสรรพากร', 'กรมสรรพากร', '💰', 'API', 'active', 'ระบบสอบถามข้อมูลภาษี การยื่นแบบ และสิทธิประโยชน์ทางภาษี', ARRAY['ภาษีเงินได้บุคคลธรรมดา','ภาษีนิติบุคคล','ภาษีมูลค่าเพิ่ม','การยื่นแบบ','สิทธิลดหย่อน'], 18320, 'hsl(213 70% 45%)', 'https://api.rd.go.th/v1'),
  (gen_random_uuid(), 'กรมการปกครอง', 'กรมการปกครอง', '🏛️', 'A2A', 'active', 'ระบบตรวจสอบข้อมูลทะเบียนราษฎร์ บัตรประชาชน และงานปกครอง', ARRAY['ทะเบียนราษฎร์','บัตรประจำตัวประชาชน','ทะเบียนบ้าน','การเปลี่ยนชื่อ','สถานะบุคคล'], 9870, 'hsl(25 85% 55%)', 'https://api.dopa.go.th/a2a'),
  (gen_random_uuid(), 'กรมที่ดิน', 'กรมที่ดิน', '🗺️', 'MCP', 'active', 'ระบบสอบถามข้อมูลที่ดิน โฉนด การจดทะเบียนสิทธิและนิติกรรม', ARRAY['โฉนดที่ดิน','การจดทะเบียน','ราคาประเมิน','การรังวัด','สิทธิและนิติกรรม'], 7650, 'hsl(280 50% 50%)', 'https://api.dol.go.th/mcp');
