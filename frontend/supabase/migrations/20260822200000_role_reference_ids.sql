-- Human-readable unique reference IDs for doctors and lab_technicians,
-- matching the existing patients.mrn pattern. Forward-only: does not edit
-- the already-applied init_roles_schema migration.

alter table public.doctors
  add column reference_id text;

alter table public.lab_technicians
  add column reference_id text;

update public.doctors
  set reference_id = 'DOC-' || upper(substr(id::text, 1, 8))
  where reference_id is null;

update public.lab_technicians
  set reference_id = 'LAB-' || upper(substr(id::text, 1, 8))
  where reference_id is null;

alter table public.doctors
  alter column reference_id set not null,
  add constraint doctors_reference_id_unique unique (reference_id);

alter table public.lab_technicians
  alter column reference_id set not null,
  add constraint lab_technicians_reference_id_unique unique (reference_id);

create index doctors_reference_id_idx on public.doctors (reference_id);
create index lab_technicians_reference_id_idx on public.lab_technicians (reference_id);

-- Update the signup trigger to populate reference_id at creation time.
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
    insert into public.doctors (id, license_number, specialty, npi, reference_id)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'license_number', ''),
      new.raw_user_meta_data ->> 'specialty',
      new.raw_user_meta_data ->> 'npi',
      'DOC-' || upper(substr(new.id::text, 1, 8))
    );
  elsif requested_role = 'patient' then
    insert into public.patients (id, mrn, date_of_birth)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'mrn', 'MRN-' || upper(substr(new.id::text, 1, 8))),
      nullif(new.raw_user_meta_data ->> 'date_of_birth', '')::date
    );
  elsif requested_role = 'lab_technician' then
    insert into public.lab_technicians (id, lab_name, certification_id, reference_id)
    values (
      new.id,
      coalesce(new.raw_user_meta_data ->> 'lab_name', ''),
      new.raw_user_meta_data ->> 'certification_id',
      'LAB-' || upper(substr(new.id::text, 1, 8))
    );
  end if;

  return new;
end;
$$;
