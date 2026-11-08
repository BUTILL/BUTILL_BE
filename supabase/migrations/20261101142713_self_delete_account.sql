create schema if not exists butill_private;
revoke all on schema butill_private from public, anon;
grant usage on schema butill_private to authenticated;

create function butill_private.delete_own_account(confirmed boolean)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
    u_id uuid := auth.uid();
    s_id text := auth.jwt() ->> 'session_id';
begin
    if confirmed is distinct from true then
        raise exception 'Account deletion requires confirmation' using errcode = '22023';
    end if;
    if u_id is null or not exists (
        select 1 from auth.sessions s
        where s.user_id = u_id and s.id::text = s_id
    ) then
        raise exception 'An active session is required' using errcode = '42501';
    end if;
    perform 1 from auth.users where id = u_id for update;
    if not found then
        raise exception 'Account not found' using errcode = '42501';
    end if;
    perform 1 from public.stores where user_id = u_id for update;
    delete from public.scenarios where store_id in (select id from public.stores where user_id = u_id);
    delete from public.analysis_runs where store_id in (select id from public.stores where user_id = u_id);
    delete from public.startup_plans where store_id in (select id from public.stores where user_id = u_id);
    delete from public.stores where user_id = u_id;
    delete from auth.sessions where user_id = u_id;
    delete from auth.users where id = u_id;
end;
$$;
revoke all on function butill_private.delete_own_account(boolean) from public, anon, authenticated;
grant execute on function butill_private.delete_own_account(boolean) to authenticated;

create function public.delete_own_account(confirmed boolean)
returns void
language sql
security invoker
set search_path = ''
as $$
    select butill_private.delete_own_account(confirmed);
$$;
revoke all on function public.delete_own_account(boolean) from public, anon, authenticated;
grant execute on function public.delete_own_account(boolean) to authenticated;
