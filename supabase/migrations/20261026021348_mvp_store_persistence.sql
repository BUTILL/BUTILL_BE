create table public.stores (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id),
    name text not null check (char_length(btrim(name)) between 1 and 100),
    business_type text not null check (business_type in ('restaurant', 'cafe')),
    region text not null check (char_length(btrim(region)) between 1 and 100),
    status text not null default 'planning' check (status in ('planning', 'operating')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index stores_user_id_idx on public.stores(user_id);

create table public.startup_plans (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null unique references public.stores(id),
    revision uuid not null default gen_random_uuid(),
    input jsonb not null check (jsonb_typeof(input) = 'object' and octet_length(input::text) <= 200000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id),
    source_revision uuid not null,
    input jsonb not null check (jsonb_typeof(input) = 'object' and octet_length(input::text) <= 200000),
    result jsonb not null check (jsonb_typeof(result) = 'object' and octet_length(result::text) <= 500000),
    created_at timestamptz not null default now(),
    unique (id, store_id)
);
create index analysis_runs_store_id_idx on public.analysis_runs(store_id);

create table public.scenarios (
    id uuid primary key default gen_random_uuid(),
    store_id uuid not null references public.stores(id),
    base_analysis_id uuid not null,
    scenario jsonb not null check (jsonb_typeof(scenario) = 'object' and octet_length(scenario::text) <= 100000),
    comparison jsonb not null check (jsonb_typeof(comparison) = 'object' and octet_length(comparison::text) <= 1000000),
    created_at timestamptz not null default now(),
    foreign key (base_analysis_id, store_id) references public.analysis_runs(id, store_id)
);
create index scenarios_store_id_idx on public.scenarios(store_id);
create index scenarios_base_analysis_idx on public.scenarios(base_analysis_id, store_id);

create function public.set_mvp_updated_at()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
    new.updated_at = pg_catalog.now();
    return new;
end;
$$;
revoke all on function public.set_mvp_updated_at() from public, anon, authenticated;
create trigger stores_updated_at before update on public.stores
for each row execute function public.set_mvp_updated_at();
create trigger startup_plans_updated_at before update on public.startup_plans
for each row execute function public.set_mvp_updated_at();

alter table public.stores enable row level security;
alter table public.startup_plans enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.scenarios enable row level security;

revoke all on public.stores, public.startup_plans, public.analysis_runs, public.scenarios from anon, authenticated;
grant select, insert, update on public.stores, public.startup_plans to authenticated;
grant select, insert on public.analysis_runs, public.scenarios to authenticated;

create policy stores_select on public.stores for select to authenticated
using (user_id = (select auth.uid()));
create policy stores_insert on public.stores for insert to authenticated
with check (user_id = (select auth.uid()));
create policy stores_update on public.stores for update to authenticated
using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

create policy plans_select on public.startup_plans for select to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy plans_insert on public.startup_plans for insert to authenticated
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy plans_update on public.startup_plans for update to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())))
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));

create policy analyses_select on public.analysis_runs for select to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy analyses_insert on public.analysis_runs for insert to authenticated
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));

create policy scenarios_select on public.scenarios for select to authenticated
using (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
create policy scenarios_insert on public.scenarios for insert to authenticated
with check (exists (select 1 from public.stores s where s.id = store_id and s.user_id = (select auth.uid())));
