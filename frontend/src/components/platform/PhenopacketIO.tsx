"use client";

import { EmptyState, fieldClass, ghostBtn, primaryBtn } from "@/components/platform/ui";

export function PhenopacketImporter({
  raw,
  onRaw,
  preview,
  error,
  onValidate,
  onImport,
  busy,
}: {
  raw: string;
  onRaw: (v: string) => void;
  preview: Record<string, unknown> | null;
  error: string | null;
  onValidate: () => void;
  onImport: () => void;
  busy?: boolean;
}) {
  return (
    <section className="card space-y-3 p-5">
      <h2 className="text-sm font-semibold">Import</h2>
      <input
        type="file"
        accept="application/json,.json"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          file.text().then(onRaw);
        }}
      />
      <textarea className={`${fieldClass()} min-h-40 font-mono text-xs`} value={raw} onChange={(e) => onRaw(e.target.value)} placeholder='{"id":"...","phenotypicFeatures":[]}' />
      <div className="flex gap-2">
        <button type="button" className={ghostBtn()} onClick={onValidate} disabled={busy}>
          Validate
        </button>
        <button type="button" className={primaryBtn()} onClick={onImport} disabled={busy}>
          Import
        </button>
      </div>
      {error && <p className="text-sm text-error">{error}</p>}
      {preview ? (
        <pre className="max-h-64 overflow-auto rounded-lg bg-panel2 p-3 text-xs">{JSON.stringify(preview, null, 2)}</pre>
      ) : (
        <EmptyState text="Choose a file and validate before import. GA4GH compliance is only claimed if the backend accepts the payload." />
      )}
    </section>
  );
}

export function PhenopacketExporter({
  caseId,
  onCaseId,
  preview,
  error,
  onPreview,
  busy,
}: {
  caseId: string;
  onCaseId: (v: string) => void;
  preview: Record<string, unknown> | null;
  error: string | null;
  onPreview: () => void;
  busy?: boolean;
}) {
  function download() {
    if (!preview) return;
    const blob = new Blob([JSON.stringify(preview, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${caseId || "phenopacket"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="card space-y-3 p-5">
      <h2 className="text-sm font-semibold">Export</h2>
      <input className={fieldClass()} value={caseId} onChange={(e) => onCaseId(e.target.value)} placeholder="Case ID" />
      <div className="flex gap-2">
        <button type="button" className={ghostBtn()} onClick={onPreview} disabled={busy}>
          Preview Phenopacket
        </button>
        <button type="button" className={primaryBtn()} onClick={download} disabled={!preview}>
          Download / export
        </button>
      </div>
      {error && <p className="text-sm text-error">{error}</p>}
      {preview ? (
        <pre className="max-h-64 overflow-auto rounded-lg bg-panel2 p-3 text-xs">{JSON.stringify(preview, null, 2)}</pre>
      ) : (
        <EmptyState text="Select a case to preview an exported phenopacket." />
      )}
    </section>
  );
}
