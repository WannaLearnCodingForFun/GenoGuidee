"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { api, type HealthReport } from "@/lib/api";

const KEYS = ["backend", "acmg", "ml", "therapy", "provenance", "database", "datasets"] as const;

function mark(status?: string): string {
  if (status === "READY") return "✓";
  if (status === "DEGRADED") return "~";
  if (status === "NOT_CONFIGURED") return "○";
  return "×";
}

function tone(status?: string): string {
  if (status === "READY") return "text-success";
  if (status === "DEGRADED" || status === "NOT_CONFIGURED") return "text-warning";
  return "text-error";
}

export default function SystemStatus() {
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api.health()
        .then((h) => {
          if (!cancelled) setHealth(h);
        })
        .catch(() => {
          if (!cancelled) {
            setHealth({
              status: "FAILED",
              ok: false,
              components: {
                backend: { status: "OFFLINE", detail: "Unable to reach :8000" },
              },
            });
          }
        });
    };
    load();
    const id = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 rounded-lg border border-navy-950/8 bg-panel2/70 px-2.5 py-1.5 text-left"
        title="System status"
      >
        <Activity className={`size-3.5 ${tone(health?.components?.backend?.status ?? (health ? "READY" : "OFFLINE"))}`} />
        <span className="truncate text-[10px] uppercase tracking-widest text-muted">
          {health ? health.status : "CHECKING"}
        </span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-2 w-56 rounded-xl border border-navy-950/10 bg-white p-3 text-[11px] shadow-lg">
          <p className="mb-2 font-semibold uppercase tracking-widest text-muted">System</p>
          {KEYS.map((key) => {
            const row = health?.components?.[key];
            return (
              <p key={key} className="flex items-center justify-between gap-2 py-0.5">
                <span className="uppercase tracking-widest text-muted">{key}</span>
                <span className={tone(row?.status)}>{mark(row?.status)} {row?.status ?? "OFFLINE"}</span>
              </p>
            );
          })}
          <p className="mt-2 text-[10px] text-muted">
            {health?.components?.backend?.status === "OFFLINE"
              ? "BACKEND OFFLINE — start FastAPI on port 8000."
              : "Ngrok is optional. Local core does not need a tunnel."}
          </p>
        </div>
      )}
    </div>
  );
}
