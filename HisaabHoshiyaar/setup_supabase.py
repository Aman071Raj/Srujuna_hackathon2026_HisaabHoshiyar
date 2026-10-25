import psycopg2

sql = """
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS user_id uuid DEFAULT auth.uid();
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS category text;
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS note text;
ALTER TABLE public.transactions ADD COLUMN IF NOT EXISTS date text;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;

DO $do$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'transactions' AND policyname = 'Users can select their own transactions'
  ) THEN
    CREATE POLICY "Users can select their own transactions" ON public.transactions FOR SELECT USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'transactions' AND policyname = 'Users can insert their own transactions'
  ) THEN
    CREATE POLICY "Users can insert their own transactions" ON public.transactions FOR INSERT WITH CHECK (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'transactions' AND policyname = 'Users can update their own transactions'
  ) THEN
    CREATE POLICY "Users can update their own transactions" ON public.transactions FOR UPDATE USING (auth.uid() = user_id);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'transactions' AND policyname = 'Users can delete their own transactions'
  ) THEN
    CREATE POLICY "Users can delete their own transactions" ON public.transactions FOR DELETE USING (auth.uid() = user_id);
  END IF;
END
$do$;
"""

conn = psycopg2.connect("postgresql://postgres.mskltxhhszqvqhbgaxbm:scupa%4012324@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute(sql)
print("SUCCESS: user_id, category, note, date columns and RLS policies created!")
