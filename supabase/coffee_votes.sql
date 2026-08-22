-- Supabase backend for the production coffee vote page.
-- Run this once in Supabase Dashboard -> SQL Editor.
-- Replace REPLACE_WITH_WEEKLY_CODE with the current vote code before running.
-- Replace REPLACE_WITH_CLEAR_TOKEN with a private admin token before running.

create table if not exists public.coffee_votes (
  week text not null default 'current',
  device_id text not null,
  drink text not null,
  name text not null default 'anomaly',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (week, device_id)
);

create table if not exists public.coffee_vote_settings (
  key text primary key,
  value text not null
);

insert into public.coffee_vote_settings (key, value)
values ('vote_code', 'REPLACE_WITH_WEEKLY_CODE')
on conflict (key) do update set value = excluded.value;

insert into public.coffee_vote_settings (key, value)
values ('clear_token', 'REPLACE_WITH_CLEAR_TOKEN')
on conflict (key) do update set value = excluded.value;

alter table public.coffee_votes enable row level security;
alter table public.coffee_vote_settings enable row level security;

drop policy if exists "coffee_votes_select" on public.coffee_votes;
create policy "coffee_votes_select"
on public.coffee_votes
for select
to anon
using (true);

create or replace function public.coffee_vote_drinks()
returns text[]
language sql
stable
as $$
  select array[
    '其他（填备注中）', '生椰拿铁', '瑞之抹茶', '鲜萃轻轻茉莉',
    '柚C美式', '精萃澳瑞白', '柠C美式', '标准美式',
    '苹果C美式', '茉莉花香拿铁', '加浓美式',
    '生椰杨枝甘露', '橙C美式', '小黄油拿铁',
    '羽衣轻体果蔬茶', '小黄油美式', '轻椰茉莉拿铁',
    '冰吸生椰拿铁', '埃塞金烘美式', '苦瓜轻体美式', '陨石拿铁'
  ];
$$;

create or replace function public.coffee_vote_list(p_week text default 'current')
returns jsonb
language sql
security definer
set search_path = public
as $$
  select coalesce(
    jsonb_object_agg(
      device_id,
      jsonb_build_object(
        'drink', drink,
        'name', name,
        'time', to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD HH24:MI')
      )
    ),
    '{}'::jsonb
  )
  from (
    select device_id, drink, name, updated_at
    from public.coffee_votes
    where week = p_week
    order by updated_at asc
  ) votes;
$$;

create or replace function public.coffee_vote_submit(
  p_week text,
  p_device_id text,
  p_drink text,
  p_name text,
  p_code text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  expected_code text;
begin
  select value into expected_code
  from public.coffee_vote_settings
  where key = 'vote_code';

  if coalesce(expected_code, '') <> '' and coalesce(p_code, '') <> expected_code then
    return jsonb_build_object('ok', false, 'error', 'Invalid vote code');
  end if;

  if p_week is null or p_week !~ '^(current|[0-9]{4}-[0-9]{2}-[0-9]{2}-[A-Za-z]{3})$' then
    return jsonb_build_object('ok', false, 'error', 'Invalid week');
  end if;

  if coalesce(p_device_id, '') = '' then
    return jsonb_build_object('ok', false, 'error', 'Missing device_id');
  end if;

  if not p_drink = any(public.coffee_vote_drinks()) then
    return jsonb_build_object('ok', false, 'error', 'Invalid drink');
  end if;

  insert into public.coffee_votes (week, device_id, drink, name, created_at, updated_at)
  values (
    left(p_week, 40),
    left(p_device_id, 120),
    p_drink,
    left(coalesce(nullif(trim(p_name), ''), 'anomaly'), 40),
    now(),
    now()
  )
  on conflict (week, device_id) do update set
    drink = excluded.drink,
    name = excluded.name,
    updated_at = now();

  return jsonb_build_object(
    'ok', true,
    'votes', public.coffee_vote_list(p_week)
  );
end;
$$;

create or replace function public.coffee_vote_cancel(
  p_week text,
  p_device_id text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.coffee_votes
  where week = p_week
    and device_id = left(coalesce(p_device_id, ''), 120);

  return jsonb_build_object(
    'ok', true,
    'votes', public.coffee_vote_list(p_week)
  );
end;
$$;

create or replace function public.coffee_vote_clear_current(p_token text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  expected_token text;
  deleted_count integer;
begin
  select value into expected_token
  from public.coffee_vote_settings
  where key = 'clear_token';

  if coalesce(expected_token, '') = '' or coalesce(p_token, '') <> expected_token then
    return jsonb_build_object('ok', false, 'error', 'Invalid admin token');
  end if;

  delete from public.coffee_votes
  where week = 'current';

  get diagnostics deleted_count = row_count;

  return jsonb_build_object(
    'ok', true,
    'cleared', deleted_count,
    'votes', public.coffee_vote_list('current')
  );
end;
$$;

grant usage on schema public to anon;
grant select on public.coffee_votes to anon;
grant execute on function public.coffee_vote_drinks() to anon;
grant execute on function public.coffee_vote_list(text) to anon;
grant execute on function public.coffee_vote_submit(text, text, text, text, text) to anon;
grant execute on function public.coffee_vote_cancel(text, text) to anon;
grant execute on function public.coffee_vote_clear_current(text) to anon;
