"use client";

import { useMemo, useState } from "react";
import { Network, X } from "lucide-react";
import type { PlatformGraph, PlatformGraphEdge, PlatformGraphNode } from "@/lib/platform/types";
import { EmptyState, SkeletonCard } from "@/components/platform/ui";

const NODE_STYLE: Record<string, { color: string; r: number }> = {
  Patient: { color: "#b4182d", r: 24 },
  Case: { color: "#54162b", r: 18 },
  Variant: { color: "#f59e0b", r: 19 },
  Gene: { color: "#fda481", r: 17 },
  Disease: { color: "#ef4444", r: 16 },
  Phenotype: { color: "#22c55e", r: 13 },
  Evidence: { color: "#94a3b8", r: 10 },
  Publication: { color: "#60a5fa", r: 12 },
  Guideline: { color: "#60a5fa", r: 13 },
  Interpretation: { color: "#b4182d", r: 16 },
};

const W = 940;
const H = 520;

interface Positioned extends PlatformGraphNode {
  x: number;
  y: number;
}

function layout(nodes: PlatformGraphNode[], edges: PlatformGraphEdge[]): Positioned[] {
  const capped = nodes.slice(0, 80);
  const pos: Positioned[] = capped.map((n, i) => {
    const angle = (i / Math.max(1, capped.length)) * Math.PI * 2;
    const r = n.type === "Variant" || n.type === "Interpretation" ? 0 : 160 + (i % 5) * 24;
    return { ...n, x: W / 2 + Math.cos(angle) * r, y: H / 2 + Math.sin(angle) * r };
  });
  const idx = new Map(pos.map((n, i) => [n.key, i]));
  for (let iter = 0; iter < 180; iter++) {
    const fx = new Array(pos.length).fill(0);
    const fy = new Array(pos.length).fill(0);
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const dx = pos[i].x - pos[j].x;
        const dy = pos[i].y - pos[j].y;
        const d2 = Math.max(120, dx * dx + dy * dy);
        const f = 22000 / d2;
        const d = Math.sqrt(d2);
        fx[i] += (dx / d) * f;
        fy[i] += (dy / d) * f;
        fx[j] -= (dx / d) * f;
        fy[j] -= (dy / d) * f;
      }
    }
    for (const e of edges) {
      const a = idx.get(e.source_key);
      const b = idx.get(e.target_key);
      if (a === undefined || b === undefined) continue;
      const dx = pos[b].x - pos[a].x;
      const dy = pos[b].y - pos[a].y;
      const d = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const f = (d - 130) * 0.012;
      fx[a] += (dx / d) * f * d * 0.02;
      fy[a] += (dy / d) * f * d * 0.02;
      fx[b] -= (dx / d) * f * d * 0.02;
      fy[b] -= (dy / d) * f * d * 0.02;
    }
    const cool = 1 - iter / 200;
    for (let i = 0; i < pos.length; i++) {
      pos[i].x += Math.max(-9, Math.min(9, fx[i] + (W / 2 - pos[i].x) * 0.004)) * cool;
      pos[i].y += Math.max(-9, Math.min(9, fy[i] + (H / 2 - pos[i].y) * 0.004)) * cool;
      pos[i].x = Math.max(40, Math.min(W - 40, pos[i].x));
      pos[i].y = Math.max(40, Math.min(H - 40, pos[i].y));
    }
  }
  return pos;
}

export default function EvidenceGraph({
  graph,
  loading,
}: {
  graph: PlatformGraph | null;
  loading?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const positioned = useMemo(
    () => (graph ? layout(graph.nodes, graph.edges) : []),
    [graph],
  );
  const selectedNode = positioned.find((n) => n.key === selected);
  const selectedEdges = graph?.edges.filter((e) => e.source_key === selected || e.target_key === selected) ?? [];

  if (loading) return <SkeletonCard />;
  if (!graph || graph.nodes.length === 0) {
    return <EmptyState text="No evidence graph neighborhood for this seed. Project ACMG evidence or interpret a variant first." />;
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <section className="card card-glow-cyan relative overflow-hidden">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" onClick={() => setSelected(null)}>
          {graph.edges.map((e, i) => {
            const a = positioned.find((n) => n.key === e.source_key);
            const b = positioned.find((n) => n.key === e.target_key);
            if (!a || !b) return null;
            const active = selected && (e.source_key === selected || e.target_key === selected);
            return (
              <line
                key={`${e.source_key}-${e.target_key}-${i}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={active ? "#b4182d" : "rgba(24,26,47,0.18)"}
                strokeWidth={active ? 2 : 1}
              />
            );
          })}
          {positioned.map((n) => {
            const style = NODE_STYLE[n.type] ?? NODE_STYLE.Evidence;
            return (
              <g
                key={n.key}
                onClick={(ev) => {
                  ev.stopPropagation();
                  setSelected(n.key);
                }}
                className="cursor-pointer"
              >
                <circle cx={n.x} cy={n.y} r={style.r} fill={style.color} opacity={0.9} />
                <text x={n.x} y={n.y + style.r + 12} textAnchor="middle" fontSize="10" fill="#37415c">
                  {n.label.slice(0, 22)}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="glass absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1 rounded-xl px-3 py-2">
          {Object.entries(NODE_STYLE).map(([k, s]) => (
            <span key={k} className="flex items-center gap-1.5 text-[10px] text-muted">
              <span className="size-2.5 rounded-full" style={{ background: s.color }} />
              {k}
            </span>
          ))}
        </div>
      </section>
      <aside className="card h-fit p-5">
        {selectedNode ? (
          <div>
            <div className="flex items-start justify-between">
              <span className="text-[10px] font-bold uppercase tracking-widest text-cyan">{selectedNode.type}</span>
              <button type="button" onClick={() => setSelected(null)} className="text-muted hover:text-fg">
                <X className="size-4" />
              </button>
            </div>
            <p className="mt-2 text-lg font-bold">{selectedNode.label}</p>
            <p className="mono mt-1 text-xs text-muted">{selectedNode.key}</p>
            <h4 className="mt-4 text-[10px] font-semibold uppercase tracking-widest text-muted">
              Connections ({selectedEdges.length})
            </h4>
            <ul className="mt-2 space-y-2 text-xs">
              {selectedEdges.map((e, i) => (
                <li key={i} className="rounded-lg border border-navy-950/8 p-2">
                  <p className="font-semibold">{e.edge_type}</p>
                  <p className="text-muted">
                    {e.source ?? "—"} · {e.direction ?? "—"} · {e.evidence_strength ?? "—"}
                  </p>
                  <p className="text-muted">retrieved {e.retrieved_at ?? "—"}</p>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="py-8 text-center text-sm text-muted">
            <Network className="mx-auto mb-3 size-8 opacity-40" />
            Select a node to inspect provenance.
          </div>
        )}
      </aside>
    </div>
  );
}
