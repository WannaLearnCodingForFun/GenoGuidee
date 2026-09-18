"use client";

import { useState } from "react";
import { TreePine } from "lucide-react";
import { platformApi } from "@/lib/platform/client";
import { humanError } from "@/lib/platform/errors";
import { writePlatformSession } from "@/lib/platform/session";
import { PhenopacketExporter, PhenopacketImporter } from "@/components/platform/PhenopacketIO";
import { PageHeader } from "@/components/platform/ui";

export default function PhenopacketsPage() {
  const [raw, setRaw] = useState("");
  const [importPreview, setImportPreview] = useState<Record<string, unknown> | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [caseId, setCaseId] = useState("");
  const [exportPreview, setExportPreview] = useState<Record<string, unknown> | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function parse(): Record<string, unknown> | null {
    try {
      const obj = JSON.parse(raw) as unknown;
      if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
        setImportError("Phenopacket JSON must be an object.");
        return null;
      }
      return obj as Record<string, unknown>;
    } catch {
      setImportError("Invalid JSON. Fix the file before validate/import.");
      return null;
    }
  }

  async function validate() {
    setImportError(null);
    const obj = parse();
    if (!obj) return;
    setBusy(true);
    try {
      const res = await platformApi.phenopacketImport(obj, caseId || undefined);
      setImportPreview(res.parsed);
    } catch (e) {
      setImportPreview(null);
      setImportError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  async function doImport() {
    await validate();
  }

  async function previewExport() {
    setExportError(null);
    if (!caseId.trim()) {
      setExportError("Enter a case ID.");
      return;
    }
    setBusy(true);
    try {
      const pkt = await platformApi.phenopacketExport(caseId.trim());
      setExportPreview(pkt);
      writePlatformSession({ caseId: caseId.trim() });
    } catch (e) {
      setExportPreview(null);
      setExportError(humanError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-10 sm:px-8">
      <PageHeader
        icon={TreePine}
        title="Phenopackets"
        subtitle="Import and export GA4GH-shaped phenopackets. Compliance is only claimed when the backend accepts the payload."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <PhenopacketImporter
          raw={raw}
          onRaw={(v) => {
            setRaw(v);
            setImportPreview(null);
            setImportError(null);
          }}
          preview={importPreview}
          error={importError}
          onValidate={() => void validate()}
          onImport={() => void doImport()}
          busy={busy}
        />
        <PhenopacketExporter
          caseId={caseId}
          onCaseId={setCaseId}
          preview={exportPreview}
          error={exportError}
          onPreview={() => void previewExport()}
          busy={busy}
        />
      </div>
    </div>
  );
}
