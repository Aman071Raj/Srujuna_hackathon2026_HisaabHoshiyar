import psycopg2

conn = psycopg2.connect("postgresql://postgres.mskltxhhszqvqhbgaxbm:scupa%4012324@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres")
conn.autocommit = True
cur = conn.cursor()
cur.execute('ALTER TABLE public.transactions ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;')
print("transactions.id default set to gen_random_uuid()::text")
