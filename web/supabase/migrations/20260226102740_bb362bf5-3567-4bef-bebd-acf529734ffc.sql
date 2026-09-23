
CREATE POLICY "Public delete conversations" ON public.conversations FOR DELETE USING (true);
CREATE POLICY "Public delete messages" ON public.messages FOR DELETE USING (true);
