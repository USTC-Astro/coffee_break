# Coffee drink menu

For an existing Supabase project, run only `coffee_drink_menu_migration.sql` once in
the Supabase SQL Editor. Do not rerun `coffee_votes.sql`: that file is for initial
setup and can change existing settings.

The migration creates `public.coffee_drink_menu` with the 20 drinks from the
current Luckin list, plus `其他（填备注中）`. It does not change current or archived
orders, the clear token, or the vote code.

After migration, use Supabase Table Editor -> `coffee_drink_menu`:

- Set `available` to `false` when a drink is unavailable; set it back to `true`
  when it returns. Do not delete its row, so it can be restored later.
- Add a drink with a unique `name`, a `sort_order` controlling its position,
  and `available = true`.
- The coffee order page reads this table through `coffee_vote_drinks()` and
  refreshes the menu every 30 seconds while open. New orders are checked
  against the same active menu in Supabase.

Past and current orders for an unavailable drink remain in the results until
they are changed or the usual manual archive/reset runs.
