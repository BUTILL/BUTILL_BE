create table public.store_settings (
    store_id uuid primary key references public.stores(id) on delete cascade,
    tax jsonb not null default '{}'::jsonb check (jsonb_typeof(tax) = 'object' and octet_length(tax::text) <= 10000),
    preferences jsonb not null default '{}'::jsonb
        check (jsonb_typeof(preferences) = 'object' and octet_length(preferences::text) <= 10000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.store_ingredient_costs (
    store_id uuid not null references public.stores(id) on delete cascade,
    price_key text not null check (price_key ~ '^[a-z_]+$'),
    unit_price integer check (unit_price > 0),
    monthly_amount bigint check (monthly_amount >= 0),
    created_at timestamptz not null default now(),
    primary key (store_id, price_key)
);

create trigger store_settings_updated_at before update on public.store_settings
for each row execute function public.set_mvp_updated_at();

alter table public.store_settings enable row level security;
alter table public.store_ingredient_costs enable row level security;

revoke all on public.store_settings, public.store_ingredient_costs from anon, authenticated;
grant select, insert, update on public.store_settings to authenticated;
grant select, insert, delete on public.store_ingredient_costs to authenticated;

create policy store_settings_select on public.store_settings for select to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy store_settings_insert on public.store_settings for insert to authenticated
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy store_settings_update on public.store_settings for update to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));

create policy ingredient_costs_select on public.store_ingredient_costs for select to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy ingredient_costs_insert on public.store_ingredient_costs for insert to authenticated
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy ingredient_costs_delete on public.store_ingredient_costs for delete to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
