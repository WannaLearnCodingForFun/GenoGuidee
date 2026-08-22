-- Public landing-page stats: aggregate account counts only (no row-level
-- data), so it's safe to expose to anon/authenticated despite RLS on the
-- underlying tables restricting row-level access to each user's own data.

create or replace function public.landing_stats()
returns table (patients bigint, doctors bigint, lab_technicians bigint)
language sql
security definer
stable
set search_path = ''
as $$
  select
    (select count(*) from public.patients) as patients,
    (select count(*) from public.doctors) as doctors,
    (select count(*) from public.lab_technicians) as lab_technicians;
$$;

grant execute on function public.landing_stats() to anon, authenticated;
