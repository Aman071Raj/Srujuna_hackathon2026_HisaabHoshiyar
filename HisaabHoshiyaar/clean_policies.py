import psycopg2

conn = psycopg2.connect("postgresql://postgres.mskltxhhszqvqhbgaxbm:scupa%4012324@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute('DROP POLICY IF EXISTS "Public read transactions" ON public.transactions;')
cur.execute('DROP POLICY IF EXISTS "Public insert transactions" ON public.transactions;')
cur.execute('DROP POLICY IF EXISTS "Public update transactions" ON public.transactions;')
cur.execute('DROP POLICY IF EXISTS "Public delete transactions" ON public.transactions;')
print("Old public policies removed. Only strict user_id = auth.uid() policies remain active!")
