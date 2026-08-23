/**
 * Supabase data layer for the VCF upload pipeline.
 *
 * Every query here runs under the caller's JWT, so row-level security decides
 * what comes back — a patient sees their own uploads, a doctor sees their
 * patients', a lab technician sees files for patients they hold an active
 * order for. There is no privileged client anywhere in this file.
 */

import { createClient } from "@/lib/supabase/client";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { api, uploadClinicalFile } from "@/lib/api";
import { parseVcf, MAX_FILE_BYTES, type ParsedVariant, type ParseResult } from "@/lib/vcf";

export const BUCKET = "vcf-uploads";

export type UploadStatus = "uploading" | "parsing" | "completed" | "failed";

export interface VcfUpload {
  id: string;
  uploader_id: string;
  patient_id: string | null;
  filename: string;
  storage_path: string;
  file_size: number;
  status: UploadStatus;
  variant_count: number;
  annotated_count: number;
  skipped_count: number;
  reference_genome: string | null;
  error_message: string | null;
  uploaded_at: string;
  parsed_at: string | null;
  sha256?: string;
  parsing_status?: string;
}

export interface UploadedVariantRow extends ParsedVariant {
  id: number;
  upload_id: string;
}

export interface PatientOption {
  id: string;
  mrn: string;
  full_name: string;
}

export interface CurrentAccount {
  id: string;
  email: string;
  full_name: string;
  role: "doctor" | "patient" | "lab_technician" | "";
}

/** Who am I, and what role do I hold? Drives the upload form's defaults. */
export async function getCurrentAccount(): Promise<CurrentAccount | null> {
  if (!isSupabaseConfigured()) {
    try {
      const u = await api.me();
      return { id: String(u.id), email: u.email, full_name: u.full_name, role: u.role as CurrentAccount["role"] };
    } catch {
      return null;
    }
  }
  const supabase = createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data: profile } = await supabase
    .from("profiles")
    .select("role, full_name")
    .eq("id", user.id)
    .single();

  return {
    id: user.id,
    email: user.email ?? "",
    full_name: profile?.full_name || user.email || "Account",
    role: (profile?.role as CurrentAccount["role"]) ?? "",
  };
}

/**
 * Patients this user may file an upload against. RLS already restricts the
 * rows, so this is simply "everything I can see".
 */
export async function listAssignablePatients(): Promise<PatientOption[]> {
  if (!isSupabaseConfigured()) {
    const rows = await api.clinicalPatients();
    return rows.map((p) => ({ id: String(p.id), mrn: p.identifier, full_name: p.diagnosis || p.identifier }));
  }
  const supabase = createClient();
  const { data, error } = await supabase
    .from("patients")
    .select("id, mrn, profiles(full_name)")
    .order("mrn");

  if (error || !data) return [];
  return data.map((row: { id: string; mrn: string; profiles: unknown }) => {
    const profile = row.profiles as unknown as { full_name: string } | { full_name: string }[] | null;
    const full_name = Array.isArray(profile) ? profile[0]?.full_name : profile?.full_name;
    return { id: row.id as string, mrn: row.mrn as string, full_name: full_name || "—" };
  });
}

/** The upload tracker feed, newest first. */
export async function listUploads(): Promise<VcfUpload[]> {
  if (!isSupabaseConfigured()) {
    const rows = await api.clinicalUploads();
    return rows.map((u) => ({
      id: String(u.id),
      uploader_id: "",
      patient_id: u.patient_id == null ? null : String(u.patient_id),
      filename: u.filename,
      storage_path: "",
      file_size: u.file_size,
      status: (u.parsing_status === "PARSED" ? "completed" : u.parsing_status === "FAILED" ? "failed" : "parsing") as UploadStatus,
      variant_count: u.variant_count,
      annotated_count: 0,
      skipped_count: 0,
      reference_genome: "GRCh38",
      error_message: u.parsing_error,
      uploaded_at: new Date(u.uploaded_at * 1000).toISOString(),
      parsed_at: null,
      sha256: u.sha256,
      parsing_status: u.parsing_status,
    }));
  }
  const supabase = createClient();
  const { data, error } = await supabase
    .from("vcf_uploads")
    .select("*")
    .order("uploaded_at", { ascending: false });

  if (error) throw new Error(error.message);
  return (data ?? []) as VcfUpload[];
}

export async function listUploadVariants(uploadId: string): Promise<UploadedVariantRow[]> {
  if (!isSupabaseConfigured()) {
    const detail = await api.clinicalUpload(Number(uploadId));
    return detail.variants.map((v) => ({
      id: v.id,
      upload_id: uploadId,
      line_number: v.id,
      chrom: v.chromosome ?? "?",
      pos: v.position ?? 0,
      ref: v.reference ?? "N",
      alt: v.alternate ?? "N",
      gene: v.gene,
      transcript: null,
      hgvs_c: v.hgvs_c,
      hgvs_p: v.hgvs_p,
      consequence: null,
      gnomad_af: null,
      cadd: null,
      revel: null,
      spliceai: null,
      phylop: null,
      qual: null,
      filter: null,
    }));
  }
  const supabase = createClient();
  const { data, error } = await supabase
    .from("uploaded_variants")
    .select("*")
    .eq("upload_id", uploadId)
    .order("id");

  if (error) throw new Error(error.message);
  return (data ?? []) as UploadedVariantRow[];
}

/** Every variant the user can see, across all accessible uploads. */
export interface AccessibleVariant extends UploadedVariantRow {
  upload: {
    filename: string;
    uploaded_at: string;
    patient_id: string | null;
  } | null;
}

export async function listAllAccessibleVariants(limit = 500): Promise<AccessibleVariant[]> {
  if (!isSupabaseConfigured()) {
    const uploads = await api.clinicalUploads();
    const out: AccessibleVariant[] = [];
    for (const u of uploads.slice(0, 20)) {
      const detail = await api.clinicalUpload(u.id);
      for (const v of detail.variants.slice(0, limit)) {
        out.push({
          id: v.id,
          upload_id: String(u.id),
          line_number: v.id,
          chrom: v.chromosome ?? "?",
          pos: v.position ?? 0,
          ref: v.reference ?? "N",
          alt: v.alternate ?? "N",
          gene: v.gene,
          transcript: null,
          hgvs_c: v.hgvs_c,
          hgvs_p: null,
          consequence: null,
          gnomad_af: null,
          cadd: null,
          revel: null,
          spliceai: null,
          phylop: null,
          qual: null,
          filter: null,
          upload: {
            filename: u.filename,
            uploaded_at: new Date(u.uploaded_at * 1000).toISOString(),
            patient_id: u.patient_id == null ? null : String(u.patient_id),
          },
        });
      }
    }
    return out;
  }
  const supabase = createClient();
  const { data, error } = await supabase
    .from("uploaded_variants")
    .select("*, upload:vcf_uploads(filename, uploaded_at, patient_id)")
    .order("id", { ascending: false })
    .limit(limit);

  if (error) throw new Error(error.message);
  return (data ?? []) as AccessibleVariant[];
}

export async function assignUploadPatient(uploadId: string, patientId: string | null): Promise<void> {
  if (!isSupabaseConfigured()) {
    await api.clinicalAssign(Number(uploadId), patientId ? Number(patientId) : null);
    return;
  }
  throw new Error("Assign via local clinical API when Supabase is not configured.");
}

export async function deleteUpload(uploadId: string, storagePath: string): Promise<void> {
  const supabase = createClient();
  // uploaded_variants cascades via the FK; the storage object does not.
  await supabase.storage.from(BUCKET).remove([storagePath]);
  const { error } = await supabase.from("vcf_uploads").delete().eq("id", uploadId);
  if (error) throw new Error(error.message);
}

export async function downloadUrl(storagePath: string): Promise<string | null> {
  const supabase = createClient();
  const { data } = await supabase.storage.from(BUCKET).createSignedUrl(storagePath, 60);
  return data?.signedUrl ?? null;
}

export interface UploadProgress {
  step: "reading" | "parsing" | "storing" | "saving" | "done";
  message: string;
  percent: number;
}

export interface UploadOutcome {
  upload: VcfUpload;
  parse: ParseResult;
}

/**
 * Full ingest: read -> parse -> store raw file -> persist parsed variants.
 *
 * The tracker row is created before the file moves, and its status is advanced
 * at each step, so a failure part-way through is visible in the tracker rather
 * than vanishing silently.
 */
export async function ingestVcf(
  file: File,
  patientId: string | null,
  onProgress: (p: UploadProgress) => void,
): Promise<UploadOutcome> {
  if (!isSupabaseConfigured()) {
    onProgress({ step: "storing", message: "Uploading to GenoGuide API…", percent: 40 });
    const row = await uploadClinicalFile(file, patientId ? Number(patientId) : null);
    onProgress({ step: "done", message: "Parsed", percent: 100 });
    return {
      upload: {
        id: String(row.id),
        uploader_id: "",
        patient_id: row.patient_id == null ? null : String(row.patient_id),
        filename: row.filename,
        storage_path: "",
        file_size: row.file_size,
        status: row.parsing_status === "PARSED" ? "completed" : "failed",
        variant_count: row.variant_count,
        annotated_count: 0,
        skipped_count: 0,
        reference_genome: "GRCh38",
        error_message: row.parsing_error,
        uploaded_at: new Date(row.uploaded_at * 1000).toISOString(),
        parsed_at: null,
      },
      parse: {
        variants: [],
        totalRecords: row.variant_count,
        skipped: 0,
        annotatedCount: 0,
        referenceGenome: "GRCh38",
        annotationSource: "none",
        errors: row.parsing_error ? [row.parsing_error] : [],
        truncated: false,
      },
    };
  }
  const supabase = createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("You must be signed in to upload.");

  if (file.size > MAX_FILE_BYTES) {
    throw new Error(
      `File is ${(file.size / 1048576).toFixed(1)} MB — the limit is ${MAX_FILE_BYTES / 1048576} MB.`,
    );
  }

  onProgress({ step: "reading", message: "Reading file…", percent: 8 });
  const text = await file.text();

  onProgress({ step: "parsing", message: "Parsing VCF records…", percent: 25 });
  const parse = parseVcf(text);

  if (!parse.variants.length) {
    throw new Error(
      parse.errors[0] ?? "No variant records found in this file. Check that it is a valid VCF.",
    );
  }

  const uploadId = crypto.randomUUID();
  const storagePath = `${user.id}/${uploadId}/${file.name}`;

  // 1. Tracker row first, so a failure below is still recorded.
  const { data: created, error: insertErr } = await supabase
    .from("vcf_uploads")
    .insert({
      id: uploadId,
      uploader_id: user.id,
      patient_id: patientId,
      filename: file.name,
      storage_path: storagePath,
      file_size: file.size,
      status: "uploading",
      reference_genome: parse.referenceGenome,
    })
    .select()
    .single();

  if (insertErr || !created) {
    throw new Error(insertErr?.message ?? "Could not create the upload record.");
  }

  // Phase B7 — append-only audit trail. Best-effort: an audit-log failure
  // must never block the actual upload.
  void supabase
    .from("profiles")
    .select("role")
    .eq("id", user.id)
    .single()
    .then(({ data: profile }: { data: { role?: string } | null }) =>
      supabase.from("audit_log").insert({
        actor_id: user.id,
        actor_role: profile?.role ?? "patient",
        action: "upload",
        resource_type: "vcf_upload",
        resource_id: uploadId,
        patient_id: patientId,
        detail: { filename: file.name },
      }),
    )
    .then((res: { error?: { message?: string } | null } | null) => {
      if (res && "error" in res && res.error) {
        console.warn("audit_log insert failed (non-fatal):", res.error.message);
      }
    });

  const fail = async (message: string): Promise<never> => {
    await supabase
      .from("vcf_uploads")
      .update({ status: "failed", error_message: message })
      .eq("id", uploadId);
    throw new Error(message);
  };

  // 2. Raw file to private storage.
  onProgress({ step: "storing", message: "Uploading file to secure storage…", percent: 45 });
  const { error: storageErr } = await supabase.storage
    .from(BUCKET)
    .upload(storagePath, file, { upsert: false, contentType: "text/plain" });

  if (storageErr) await fail(`Storage upload failed: ${storageErr.message}`);

  // 3. Parsed variants, in batches.
  onProgress({ step: "saving", message: "Saving parsed variants…", percent: 65 });
  await supabase.from("vcf_uploads").update({ status: "parsing" }).eq("id", uploadId);

  const BATCH = 500;
  for (let i = 0; i < parse.variants.length; i += BATCH) {
    const chunk = parse.variants.slice(i, i + BATCH).map((v) => ({ upload_id: uploadId, ...v }));
    const { error: rowsErr } = await supabase.from("uploaded_variants").insert(chunk);
    if (rowsErr) await fail(`Saving variants failed: ${rowsErr.message}`);
    onProgress({
      step: "saving",
      message: `Saving parsed variants… ${Math.min(i + BATCH, parse.variants.length)}/${parse.variants.length}`,
      percent: 65 + Math.round(30 * ((i + BATCH) / parse.variants.length)),
    });
  }

  // 4. Seal the tracker row.
  const { data: finished, error: finishErr } = await supabase
    .from("vcf_uploads")
    .update({
      status: "completed",
      variant_count: parse.variants.length,
      annotated_count: parse.annotatedCount,
      skipped_count: parse.skipped,
      parsed_at: new Date().toISOString(),
    })
    .eq("id", uploadId)
    .select()
    .single();

  if (finishErr || !finished) await fail(finishErr?.message ?? "Could not finalize the upload.");

  onProgress({ step: "done", message: "Upload complete.", percent: 100 });
  return { upload: finished as VcfUpload, parse };
}
