
-- 1. Create conversations table
CREATE TABLE public.conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  preview text NOT NULL DEFAULT '',
  agencies text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'success',
  message_count int NOT NULL DEFAULT 0,
  response_time text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 2. Create messages table
CREATE TABLE public.messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid REFERENCES public.conversations(id) ON DELETE CASCADE NOT NULL,
  role text NOT NULL,
  content text NOT NULL,
  agent_steps jsonb,
  sources jsonb,
  rating text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 3. Enable RLS
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;

-- 4. Public read + insert policies (no auth yet)
CREATE POLICY "Public read conversations" ON public.conversations FOR SELECT USING (true);
CREATE POLICY "Public insert conversations" ON public.conversations FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update conversations" ON public.conversations FOR UPDATE USING (true);

CREATE POLICY "Public read messages" ON public.messages FOR SELECT USING (true);
CREATE POLICY "Public insert messages" ON public.messages FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update messages" ON public.messages FOR UPDATE USING (true);

-- 5. Index for faster queries
CREATE INDEX idx_conversations_created_at ON public.conversations(created_at DESC);
CREATE INDEX idx_messages_conversation_id ON public.messages(conversation_id);
