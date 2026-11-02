-- Run this file once in Supabase SQL Editor for the existing coffee order site.
-- It does not modify votes, history, vote_code, or clear_token.

begin;

create table if not exists public.coffee_drink_menu (
  name text primary key,
  sort_order integer not null,
  available boolean not null default true
);

insert into public.coffee_drink_menu (name, sort_order) values
  ('小黄油美式（原创）', 1), ('生椰拿铁（原创）', 2),
  ('橙C美式（原创）', 3), ('小黄油拿铁（原创）', 4),
  ('生椰杨枝甘露', 5), ('加浓美式', 6), ('小苹果茉莉冰奶', 7), ('柚C美式', 8),
  ('苹果C美式', 9), ('咸芝士豆乳鸳鸯拿铁', 10), ('标准美式', 11),
  ('茉莉花香拿铁', 12), ('羽衣轻体果蔬茶', 13), ('鲜萃轻轻茉莉', 14),
  ('精萃澳瑞白', 15), ('紫葡萄茉莉冰奶', 16), ('乳酸菌美式', 17),
  ('经典泰奶', 18), ('埃塞金烘拿铁', 19), ('埃塞金烘美式', 20),
  ('其他（填备注中）', 21)
on conflict (name) do nothing;

alter table public.coffee_drink_menu enable row level security;

create or replace function public.coffee_vote_drinks()
returns text[]
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(array_agg(name order by sort_order, name), array[]::text[])
  from public.coffee_drink_menu
  where available;
$$;

grant execute on function public.coffee_vote_drinks() to anon;

commit;
