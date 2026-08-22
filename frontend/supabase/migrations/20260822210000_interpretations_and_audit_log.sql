-- Phase B5/B7: minimal persisted interpretation record (for the therapy
-- sign-off gate) + an append-only audit_log table.

create table public.interpretations (
  id bigint generated always as identity primary key,
  patient_id uuid not null references public.patients (id) on delete cascade,
  variant text not null,
  acmg_classification text not null,
  therapy_addressable boolean not null default false,
  reviewed_by uuid references public.doctors (id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);

create index interpretations_patient_id_idx on public.interpretations (patient_id);
create index interpretations_reviewed_by_idx on public.interpretations (reviewed_by);

alter table public.interpretations enable row level security;

create policy "interpretations_select_own"
  on public.interpretations for select
  to authenticated
  using ((select auth.uid()) = patient_id);

create policy "interpretations_select_by_treating_doctor"
  on public.interpretations for select
  to authenticated
  using (private.is_patients_doctor(patient_id));

create policy "interpretations_insert_by_treating_doctor"
  on public.interpretations for insert
  to authenticated
  with check (private.is_patients_doctor(patient_id));

create policy "interpretations_update_by_treating_doctor"
  on public.interpretations for update
  to authenticated
  using (private.is_patients_doctor(patient_id))
  with check (private.is_patients_doctor(patient_id));

grant select, insert, update on public.interpretations to authenticated;
grant usage, select on sequence public.interpretations_id_seq to authenticated;

-- ---------------------------------------------------------------------------
-- audit_log: append-only. No client role may UPDATE or DELETE a row, ever —
-- authorization is enforced by grants (no update/delete privilege exists),
-- not just RLS, so even a future permissive policy can't reopen it.
-- ---------------------------------------------------------------------------

create table public.audit_log (
  id bigint generated always as identity primary key,
  actor_id uuid not null references auth.users (id) on delete set null,
  actor_role public.app_role not null,
  action text not null,
  resource_type text not null,
  resource_id text,
  patient_id uuid references public.patients (id) on delete set null,
  at timestamptz not null default now(),
  detail jsonb not null default '{}'::jsonb
);

create index audit_log_patient_id_idx on public.audit_log (patient_id);
create index audit_log_actor_id_idx on public.audit_log (actor_id);
create index audit_log_at_idx on public.audit_log (at);

alter table public.audit_log enable row level security;

create policy "audit_log_select_own_actions"
  on public.audit_log for select
  to authenticated
  using ((select auth.uid()) = actor_id);

create policy "audit_log_select_own_records_as_patient"
  on public.audit_log for select
  to authenticated
  using ((select auth.uid()) = patient_id);

create policy "audit_log_insert_own"
  on public.audit_log for insert
  to authenticated
  with check ((select auth.uid()) = actor_id);

-- Append-only by construction: grant insert + select only. update/delete are
-- never granted to authenticated, and are revoked from public/anon for
-- defense in depth even though neither has table access at all otherwise.
revoke all on public.audit_log from public, anon;
grant select, insert on public.audit_log to authenticated;
grant usage, select on sequence public.audit_log_id_seq to authenticated;
revoke update, delete on public.audit_log from authenticated;
