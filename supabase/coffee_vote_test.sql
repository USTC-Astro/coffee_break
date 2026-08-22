-- Supabase smoke-test table for the coffee-break GitHub Pages frontend.
-- Run this once in Supabase Dashboard -> SQL Editor.

create table if not exists public.coffee_vote_test (
  id bigserial primary key,
  name text not null default 'anonymous',
  note text,
  user_agent text,
  created_at timestamptz not null default now()
);

alter table public.coffee_vote_test enable row level security;

drop policy if exists "coffee_vote_test_select" on public.coffee_vote_test;
create policy "coffee_vote_test_select"
on public.coffee_vote_test
for select
to anon
using (true);

drop policy if exists "coffee_vote_test_insert" on public.coffee_vote_test;
create policy "coffee_vote_test_insert"
on public.coffee_vote_test
for insert
to anon
with check (true);
