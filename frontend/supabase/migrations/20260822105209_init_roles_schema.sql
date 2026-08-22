-- GenoGuide roles & auth schema
-- Three distinct account types: doctor, patient, lab_technician.
-- profiles.role is the single source of truth for authorization (never
-- user_metadata, which is client-editable) and is looked up via a
-- SECURITY DEFINER helper kept out of the exposed `public` schema.

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create type public.app_role as enum ('doctor', 'patient', 'lab_technician');
create type public.lab_order_status as enum ('pending', 'in_progress', 'completed', 'cancelled');

-- ---------------------------------------------------------------------------
-- profiles: one row per auth.users, created by the signup trigger below.
-- ---------------------------------------------------------------------------

create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role public.app_role not null,
  full_name text not null default '',
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

-- ---------------------------------------------------------------------------
-- Role-specific detail tables. Each row's id IS the profile/auth.users id.
-- ---------------------------------------------------------------------------

create table public.doctors (
  id uuid primary key references public.profiles (id) on delete cascade,
  license_number text not null default '',
  specialty text,
  npi text,
  created_at timestamptz not null default now()
);

alter table public.doctors enable row level security;

create table public.patients (
  id uuid primary key references public.profiles (id) on delete cascade,
  mrn text not null unique,
  date_of_birth date,
  primary_doctor_id uuid references public.doctors (id) on delete set null,
  created_at timestamptz not null default now()
);

create index patients_primary_doctor_id_idx on public.patients (primary_doctor_id);

alter table public.patients enable row level security;

create table public.lab_technicians (
  id uuid primary key references public.profiles (id) on delete cascade,
  lab_name text not null default '',
  certification_id text,
  created_at timestamptz not null default now()
);

alter table public.lab_technicians enable row level security;

-- ---------------------------------------------------------------------------
-- lab_orders: the legitimate-access link between a lab technician and a
-- specific patient (a technician can only see patients they have an order
-- for — not the whole patient roster).
-- ---------------------------------------------------------------------------

create table public.lab_orders (
  id bigint generated always as identity primary key,
  patient_id uuid not null references public.patients (id) on delete cascade,
  ordering_doctor_id uuid not null references public.doctors (id) on delete restrict,
  lab_technician_id uuid references public.lab_technicians (id) on delete set null,
  variant_id text,
  status public.lab_order_status not null default 'pending',
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index lab_orders_patient_id_idx on public.lab_orders (patient_id);
create index lab_orders_ordering_doctor_id_idx on public.lab_orders (ordering_doctor_id);
create index lab_orders_lab_technician_id_idx on public.lab_orders (lab_technician_id);

alter table public.lab_orders enable row level security;

-- ---------------------------------------------------------------------------
-- Private helper functions used by RLS policies (indexed lookups, not
-- per-row auth.uid() calls). Kept in `private` so they are never reachable
-- as public RPC endpoints.
-- ---------------------------------------------------------------------------

create or replace function private.current_role()
returns public.app_role
language sql
security definer
stable
set search_path = ''
as $$
  select role from public.profiles where id = (select auth.uid());
$$;

revoke execute on function private.current_role() from public, anon, authenticated;
grant execute on function private.current_role() to authenticated;

create or replace function private.is_patients_doctor(target_patient_id uuid)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.patients
    where id = target_patient_id
      and primary_doctor_id = (select auth.uid())
  );
$$;

revoke execute on function private.is_patients_doctor(uuid) from public, anon, authenticated;
grant execute on function private.is_patients_doctor(uuid) to authenticated;

create or replace function private.has_lab_order_for(target_patient_id uuid)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.lab_orders
    where patient_id = target_patient_id
      and lab_technician_id = (select auth.uid())
      and status in ('pending', 'in_progress')
  );
$$;

revoke execute on function private.has_lab_order_for(uuid) from public, anon, authenticated;
grant execute on function private.has_lab_order_for(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Signup trigger: fans a new auth.users row out into profiles + the
-- matching role-detail row. Requires raw_user_meta_data.role to be a valid
-- app_role — signup fails otherwise, so every account is created with one
-- of the three roles by construction.
-- ---------------------------------------------------------------------------

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  requested_role public.app_role;
begin
  requested_role := (new.raw_user_meta_data ->> 'role')::public.app_role;

  insert into public.profiles (id, role, full_name)
  values (new.id, requested_role, coalesce(new.raw_user_meta_data ->> 'full_name', ''));

  if requested_role = 'doctor' then
    insert into public.doctors (id, license_number, specialty, npi)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'license_number', ''),
      new.raw_user_meta_data ->> 'specialty',
      new.raw_user_meta_data ->> 'npi'
    );
  elsif requested_role = 'patient' then
    insert into public.patients (id, mrn, date_of_birth)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'mrn', 'MRN-' || upper(substr(new.id::text, 1, 8))),
      nullif(new.raw_user_meta_data ->> 'date_of_birth', '')::date
    );
  elsif requested_role = 'lab_technician' then
    insert into public.lab_technicians (id, lab_name, certification_id)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'lab_name', ''),
      new.raw_user_meta_data ->> 'certification_id'
    );
  end if;

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function private.handle_new_user();

-- role is immutable after signup — enforced in a trigger because RLS
-- WITH CHECK cannot reference the pre-update row.
create or replace function private.prevent_role_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if new.role <> old.role then
    raise exception 'role cannot be changed after signup';
  end if;
  return new;
end;
$$;

create trigger profiles_prevent_role_change
  before update on public.profiles
  for each row execute function private.prevent_role_change();

-- ---------------------------------------------------------------------------
-- RLS policies
-- ---------------------------------------------------------------------------

-- profiles
create policy "profiles_select_own"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "profiles_select_as_treating_doctor"
  on public.profiles for select
  to authenticated
  using (
    (select private.current_role()) = 'doctor'
    and private.is_patients_doctor(id)
  );

create policy "profiles_select_as_lab_technician"
  on public.profiles for select
  to authenticated
  using (
    (select private.current_role()) = 'lab_technician'
    and private.has_lab_order_for(id)
  );

create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- doctors
create policy "doctors_select_own"
  on public.doctors for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "doctors_select_by_their_patients"
  on public.doctors for select
  to authenticated
  using (
    exists (
      select 1 from public.patients
      where patients.primary_doctor_id = doctors.id
        and patients.id = (select auth.uid())
    )
  );

create policy "doctors_update_own"
  on public.doctors for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- patients
create policy "patients_select_own"
  on public.patients for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "patients_select_by_treating_doctor"
  on public.patients for select
  to authenticated
  using ((select auth.uid()) = primary_doctor_id);

create policy "patients_select_by_lab_technician"
  on public.patients for select
  to authenticated
  using (private.has_lab_order_for(id));

create policy "patients_update_own"
  on public.patients for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create policy "patients_update_by_treating_doctor"
  on public.patients for update
  to authenticated
  using ((select auth.uid()) = primary_doctor_id)
  with check ((select auth.uid()) = primary_doctor_id);

-- lab_technicians
create policy "lab_technicians_select_own"
  on public.lab_technicians for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "lab_technicians_update_own"
  on public.lab_technicians for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

-- lab_orders
create policy "lab_orders_select_patient"
  on public.lab_orders for select
  to authenticated
  using ((select auth.uid()) = patient_id);

create policy "lab_orders_select_ordering_doctor"
  on public.lab_orders for select
  to authenticated
  using ((select auth.uid()) = ordering_doctor_id);

create policy "lab_orders_select_assigned_technician"
  on public.lab_orders for select
  to authenticated
  using ((select auth.uid()) = lab_technician_id);

create policy "lab_orders_insert_by_doctor"
  on public.lab_orders for insert
  to authenticated
  with check (
    (select private.current_role()) = 'doctor'
    and ordering_doctor_id = (select auth.uid())
    and private.is_patients_doctor(patient_id)
  );

create policy "lab_orders_update_by_ordering_doctor"
  on public.lab_orders for update
  to authenticated
  using ((select auth.uid()) = ordering_doctor_id)
  with check ((select auth.uid()) = ordering_doctor_id);

create policy "lab_orders_update_by_assigned_technician"
  on public.lab_orders for update
  to authenticated
  using ((select auth.uid()) = lab_technician_id)
  with check ((select auth.uid()) = lab_technician_id);

-- ---------------------------------------------------------------------------
-- Data API exposure. RLS (above) restricts rows; these grants restrict which
-- privileges the `authenticated` role has on the tables at all. Note that
-- profiles/doctors/patients/lab_technicians rows are only ever created by
-- the SECURITY DEFINER signup trigger, so `authenticated` gets no INSERT.
-- ---------------------------------------------------------------------------

grant usage on schema public to authenticated;
grant select, update on public.profiles to authenticated;
grant select, update on public.doctors to authenticated;
grant select, update on public.patients to authenticated;
grant select, update on public.lab_technicians to authenticated;
grant select, insert, update on public.lab_orders to authenticated;
grant usage, select on sequence public.lab_orders_id_seq to authenticated;
