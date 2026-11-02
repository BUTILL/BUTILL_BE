create table public.ingredients (
    id uuid primary key default gen_random_uuid(),
    key text not null unique check (key ~ '^[a-z_]+$'),
    name text not null check (char_length(btrim(name)) between 1 and 60),
    groups text[] not null,
    source text not null default 'KAMIS',
    category_code text not null,
    item_code text not null,
    kind_code text,
    rank_code text,
    product_class text not null,
    region_code text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.ingredient_prices (
    id uuid primary key default gen_random_uuid(),
    ingredient_id uuid not null references public.ingredients(id),
    price_date date not null,
    kind_code text not null,
    kind_name text,
    rank_code text not null,
    rank_name text,
    unit text not null,
    market_code text not null,
    market_name text,
    price integer not null check (price > 0),
    price_per_kg integer check (price_per_kg > 0),
    source text not null default 'KAMIS',
    collected_at timestamptz not null,
    unique (ingredient_id, price_date, kind_code, rank_code, market_code)
);
create index ingredient_prices_lookup_idx on public.ingredient_prices(ingredient_id, price_date);

create table public.price_collection_runs (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'KAMIS',
    started_at timestamptz not null,
    finished_at timestamptz not null,
    status text not null check (status in ('success', 'partial', 'failed')),
    success_count integer not null check (success_count >= 0),
    failure_count integer not null check (failure_count >= 0),
    saved_count integer not null default 0 check (saved_count >= 0),
    error_code text,
    item_results jsonb not null default '[]'::jsonb check (jsonb_typeof(item_results) = 'array')
);
create index price_collection_runs_started_idx on public.price_collection_runs(started_at desc);

create trigger ingredients_updated_at before update on public.ingredients
for each row execute function public.set_mvp_updated_at();

alter table public.ingredients enable row level security;
alter table public.ingredient_prices enable row level security;
alter table public.price_collection_runs enable row level security;

revoke all on public.ingredients, public.ingredient_prices, public.price_collection_runs from anon, authenticated;
grant select on public.ingredients, public.ingredient_prices, public.price_collection_runs to anon, authenticated;
grant select, insert, update on public.ingredients, public.ingredient_prices, public.price_collection_runs to service_role;

create policy ingredients_read on public.ingredients for select to anon, authenticated using (true);
create policy ingredient_prices_read on public.ingredient_prices for select to anon, authenticated using (true);
create policy price_runs_read on public.price_collection_runs for select to anon, authenticated using (true);
