-- GenoGuide VCF upload pipeline.
--
-- A hospital user (doctor or lab technician) or a patient uploads a VCF file.
-- The raw file goes to a PRIVATE storage bucket; the parsed variant rows go to
-- public.uploaded_variants. Access follows the same rules as the rest of the
-- schema: you can reach an upload if you made it, if it is about you, if you
-- are the patient's treating doctor, or if you hold an active lab order for
-- that patient.

create type public.upload_status as enum ('uploading', 'parsing', 'completed', 'failed');

-- ---------------------------------------------------------------------------
-- vcf_uploads: one row per uploaded file. This table IS the upload tracker.
-- ---------------------------------------------------------------------------

create table public.vcf_uploads (
  id uuid primary key default gen_random_uuid(),
  uploader_id uuid not null references public.profiles (id) on delete cascade,
  -- Which patient the file is about. Null means "unassigned" (e.g. a lab tech
  -- uploading before the order is linked). A patient uploading their own file
  -- sets this to their own id.
  patient_id uuid references public.patients (id) on delete set null,
  filename text not null,
  storage_path text not null unique,
  file_size bigint not null default 0,
  status public.upload_status not null default 'uploading',
  variant_count integer not null default 0,
  -- How many parsed variants carried at least one in-silico annotation
  -- (CADD/REVEL/SpliceAI/phyloP). Drives the "annotation completeness" hint.
  annotated_count integer not null default 0,
  skipped_count integer not null default 0,
  reference_genome text,
  error_message text,
  uploaded_at timestamptz not null default now(),
  parsed_at timestamptz
);

create index vcf_uploads_uploader_id_idx on public.vcf_uploads (uploader_id);
create index vcf_uploads_patient_id_idx on public.vcf_uploads (patient_id);
create index vcf_uploads_uploaded_at_idx on public.vcf_uploads (uploaded_at desc);

alter table public.vcf_uploads enable row level security;

-- ---------------------------------------------------------------------------
-- uploaded_variants: parsed VCF records, normalized onto the same annotation
-- shape the ACMG rule engine and the XGBoost feature builder consume.
-- ---------------------------------------------------------------------------

create table public.uploaded_variants (
  id bigint generated always as identity primary key,
  upload_id uuid not null references public.vcf_uploads (id) on delete cascade,
  line_number integer,
  chrom text not null,
  pos bigint not null,
  ref text not null,
  alt text not null,
  gene text,
  transcript text,
  hgvs_c text,
  hgvs_p text,
  consequence text,
  gnomad_af double precision,
  cadd double precision,
  revel double precision,
  spliceai double precision,
  phylop double precision,
  qual double precision,
  filter text,
  created_at timestamptz not null default now()
);

create index uploaded_variants_upload_id_idx on public.uploaded_variants (upload_id);
create index uploaded_variants_gene_idx on public.uploaded_variants (gene);

alter table public.uploaded_variants enable row level security;

-- ---------------------------------------------------------------------------
-- Access helpers. Kept in `private` so they are never reachable as RPC, and
-- SECURITY DEFINER so they can read the lookup tables without recursing into
-- the calling user's RLS policies.
-- ---------------------------------------------------------------------------

create or replace function private.can_access_upload(target_uploader_id uuid, target_patient_id uuid)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select
    -- you uploaded it
    target_uploader_id = (select auth.uid())
    -- it is about you
    or (target_patient_id is not null and target_patient_id = (select auth.uid()))
    -- you are the patient's treating doctor
    or (
      target_patient_id is not null
      and (select private.current_role()) = 'doctor'
      and private.is_patients_doctor(target_patient_id)
    )
    -- you hold an active lab order for the patient
    or (
      target_patient_id is not null
      and (select private.current_role()) = 'lab_technician'
      and private.has_lab_order_for(target_patient_id)
    );
$$;

revoke execute on function private.can_access_upload(uuid, uuid) from public, anon, authenticated;
grant execute on function private.can_access_upload(uuid, uuid) to authenticated;

create or replace function private.can_access_upload_id(target_upload_id uuid)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select exists (
    select 1 from public.vcf_uploads u
    where u.id = target_upload_id
      and private.can_access_upload(u.uploader_id, u.patient_id)
  );
$$;

revoke execute on function private.can_access_upload_id(uuid) from public, anon, authenticated;
grant execute on function private.can_access_upload_id(uuid) to authenticated;

-- Can the current user file an upload against this patient? Uploading a file
-- about someone else is a write, so it is deliberately stricter than reading.
create or replace function private.can_upload_for(target_patient_id uuid)
returns boolean
language sql
security definer
stable
set search_path = ''
as $$
  select
    target_patient_id is null
    or target_patient_id = (select auth.uid())
    or (
      (select private.current_role()) = 'doctor'
      and private.is_patients_doctor(target_patient_id)
    )
    or (
      (select private.current_role()) = 'lab_technician'
      and private.has_lab_order_for(target_patient_id)
    );
$$;

revoke execute on function private.can_upload_for(uuid) from public, anon, authenticated;
grant execute on function private.can_upload_for(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- RLS: vcf_uploads
-- ---------------------------------------------------------------------------

create policy "vcf_uploads_select_accessible"
  on public.vcf_uploads for select
  to authenticated
  using (private.can_access_upload(uploader_id, patient_id));

create policy "vcf_uploads_insert_own"
  on public.vcf_uploads for insert
  to authenticated
  with check (
    uploader_id = (select auth.uid())
    and private.can_upload_for(patient_id)
  );

-- Only the uploader advances status / counts as parsing completes.
create policy "vcf_uploads_update_own"
  on public.vcf_uploads for update
  to authenticated
  using (uploader_id = (select auth.uid()))
  with check (
    uploader_id = (select auth.uid())
    and private.can_upload_for(patient_id)
  );

create policy "vcf_uploads_delete_own"
  on public.vcf_uploads for delete
  to authenticated
  using (uploader_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- RLS: uploaded_variants — visibility inherited from the parent upload.
-- ---------------------------------------------------------------------------

create policy "uploaded_variants_select_accessible"
  on public.uploaded_variants for select
  to authenticated
  using (private.can_access_upload_id(upload_id));

create policy "uploaded_variants_insert_own_upload"
  on public.uploaded_variants for insert
  to authenticated
  with check (
    exists (
      select 1 from public.vcf_uploads u
      where u.id = upload_id
        and u.uploader_id = (select auth.uid())
    )
  );

create policy "uploaded_variants_delete_own_upload"
  on public.uploaded_variants for delete
  to authenticated
  using (
    exists (
      select 1 from public.vcf_uploads u
      where u.id = upload_id
        and u.uploader_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- Private storage bucket for the raw .vcf files.
-- Object key convention: {uploader_id}/{upload_id}/{filename}
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'vcf-uploads',
  'vcf-uploads',
  false,
  52428800, -- 50 MB
  null      -- VCF has no registered MIME type; browsers send text/plain, application/octet-stream, or ''
)
on conflict (id) do nothing;

-- Write only into your own folder.
create policy "vcf_objects_insert_own_folder"
  on storage.objects for insert
  to authenticated
  with check (
    bucket_id = 'vcf-uploads'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- Read anything you are allowed to see the upload row for.
create policy "vcf_objects_select_accessible"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'vcf-uploads'
    and (
      (storage.foldername(name))[1] = (select auth.uid())::text
      or exists (
        select 1 from public.vcf_uploads u
        where u.storage_path = storage.objects.name
          and private.can_access_upload(u.uploader_id, u.patient_id)
      )
    )
  );

create policy "vcf_objects_delete_own_folder"
  on storage.objects for delete
  to authenticated
  using (
    bucket_id = 'vcf-uploads'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

-- ---------------------------------------------------------------------------
-- Grants. RLS decides rows; these decide privileges.
-- ---------------------------------------------------------------------------

grant select, insert, update, delete on public.vcf_uploads to authenticated;
grant select, insert, delete on public.uploaded_variants to authenticated;
grant usage, select on sequence public.uploaded_variants_id_seq to authenticated;
