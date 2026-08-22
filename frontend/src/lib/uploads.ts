/**
 * Supabase data layer for the VCF upload pipeline.
 *
 * Every query here runs under the caller's JWT, so row-level security decides
 * what comes back — a patient sees their own uploads, a doctor sees their
 * patients', a lab technician sees files for patients they hold an active
 * order for. There is no privileged client anywhere in this file.
 */

import { createClient } from "@/lib/supabase/client";
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
  const supabase = createClient();
  const { data, error } = await supabase
    .from("patients")
    .select("id, mrn, profiles(full_name)")
    .order("mrn");

  if (error || !data) return [];
  return data.map((row) => {
    const profile = row.profiles as unknown as { full_name: string } | { full_name: string }[] | null;
    const full_name = Array.isArray(profile) ? profile[0]?.full_name : profile?.full_name;
    return { id: row.id as string, mrn: row.mrn as string, full_name: full_name || "—" };
  });
}

/** The upload tracker feed, newest first. */
export async function listUploads(): Promise<VcfUpload[]> {
  const supabase = createClient();
  const { data, error } = await supabase
    .from("vcf_uploads")
    .select("*")
    .order("uploaded_at", { ascending: false });

  if (error) throw new Error(error.message);
  return (data ?? []) as VcfUpload[];
}

export async function listUploadVariants(uploadId: string): Promise<UploadedVariantRow[]> {
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
  const supabase = createClient();
  const { data, error } = await supabase
    .from("uploaded_variants")
    .select("*, upload:vcf_uploads(filename, uploaded_at, patient_id)")
    .order("id", { ascending: false })
    .limit(limit);

  if (error) throw new Error(error.message);
  return (data ?? []) as AccessibleVariant[];
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
