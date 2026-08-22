-- Defense in depth for the upload tables.
--
-- Supabase's bootstrap runs
--   alter default privileges in schema public grant all on tables to anon, authenticated, ...
-- so every new table in `public` starts with table-level privileges for the
-- anonymous role. RLS is what actually stops anon reading rows, and it does
-- (verified: an anonymous insert is refused with 42501). But that makes RLS
-- the single thing standing between an unauthenticated request and patient
-- genomic data.
--
-- These tables hold parsed patient variants, so remove the privilege as well
-- as the policy. After this, an anonymous request fails at the privilege
-- check and never reaches RLS at all — a policy bug can no longer expose
-- anything to anon.
--
-- No effect on the app: every query in lib/uploads.ts runs as `authenticated`.

revoke all on public.vcf_uploads from anon;
revoke all on public.uploaded_variants from anon;
revoke all on sequence public.uploaded_variants_id_seq from anon;
