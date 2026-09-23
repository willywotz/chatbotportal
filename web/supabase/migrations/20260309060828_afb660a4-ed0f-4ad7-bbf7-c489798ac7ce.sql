ALTER TABLE public.agencies
  ADD COLUMN IF NOT EXISTS auth_method text DEFAULT 'api_key',
  ADD COLUMN IF NOT EXISTS auth_header text DEFAULT '',
  ADD COLUMN IF NOT EXISTS base_path text DEFAULT '',
  ADD COLUMN IF NOT EXISTS rate_limit_rpm integer DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS request_format text DEFAULT 'json',
  ADD COLUMN IF NOT EXISTS api_endpoints jsonb DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS api_spec_raw text DEFAULT NULL;