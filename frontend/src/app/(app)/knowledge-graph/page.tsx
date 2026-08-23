"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Network, X } from "lucide-react";
import { api, type GraphEdge, type GraphNode } from "@/lib/api";
import { useAccount } from "@/lib/useAccount";

const NODE_STYLE: Record<string, { color: string; r: number; label: string }> = {
  patient: { color: "#b4182d", r: 26, label: "Patient" },
  variant: { color: "#f59e0b", r: 19, label: "Variant" },
  gene: { color: "#fda481", r: 17, label: "Gene" },
  disease: { color: "#ef4444", r: 16, label: "Disease" },
  phenotype: { color: "#22c55e", r: 13, label: "Phenotype" },
  drug: { color: "#f472b6", r: 13, label: "Drug" },
  guideline: { color: "#60a5fa", r: 13, label: "Guideline" },
  evidence: { color: "#94a3b8", r: 10, label: "Evidence" },
};

const W = 940;
const H = 620;

interface PositionedNode extends GraphNode {
  x: number;
  y: number;
}

/** Deterministic force-directed layout computed synchronously. */
function layout(nodes: GraphNode[], edges: GraphEdge[]): PositionedNode[] {
  const pos: PositionedNode[] = nodes.map((n, i) => {
    const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2;
    const r = n.type === "patient" ? 0 : 180 + (i % 5) * 28;
    return { ...n, x: W / 2 + Math.cos(angle) * r, y: H / 2 + Math.sin(angle) * r };
  });
  const idx = new Map(pos.map((n, i) => [n.id, i]));

  for (let iter = 0; iter < 320; iter++) {
    const fx = new Array(pos.length).fill(0);
    const fy = new Array(pos.length).fill(0);

    // Pairwise repulsion
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const dx = pos[i].x - pos[j].x;
        const dy = pos[i].y - pos[j].y;
        const d2 = Math.max(120, dx * dx + dy * dy);
        const f = 26000 / d2;
        const d = Math.sqrt(d2);
        fx[i] += (dx / d) * f;
        fy[i] += (dy / d) * f;
        fx[j] -= (dx / d) * f;
        fy[j] -= (dy / d) * f;
      }
    }
    // Edge springs
    for (const e of edges) {
      const a = idx.get(e.source);
      const b = idx.get(e.target);
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
    // Centering gravity + integrate
    const cool = 1 - iter / 340;
    for (let i = 0; i < pos.length; i++) {
      fx[i] += (W / 2 - pos[i].x) * 0.004;
      fy[i] += (H / 2 - pos[i].y) * 0.004;
      pos[i].x += Math.max(-9, Math.min(9, fx[i])) * cool;
      pos[i].y += Math.max(-9, Math.min(9, fy[i])) * cool;
      pos[i].x = Math.max(50, Math.min(W - 50, pos[i].x));
      pos[i].y = Math.max(46, Math.min(H - 46, pos[i].y));
    }
  }
  return pos;
}

// Demo fallback only — used when no authenticated patient context exists
// (logged-out/demo browsing of the showcase dataset).
export default function KnowledgeGraph() {
  const { account, loading } = useAccount();
  const [patientIds, setPatientIds] = useState<{ id: number; identifier: string }[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<number | null>(null);
  const [graph, setGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (loading || !account) return;
    api.clinicalPatients()
      .then((ps) => {
        setPatientIds(ps.map((p) => ({ id: p.id, identifier: p.identifier })));
        setSelectedPatient((prev) => prev ?? ps[0]?.id ?? null);
      })
      .catch(() => setError(true));
  }, [account, loading]);

  useEffect(() => {
    if (selectedPatient == null) return;
    setGraph(null);
    setSelectedNode(null);
    api.clinicalGraph(selectedPatient).then(setGraph).catch(() => setError(true));
  }, [selectedPatient]);

  const positioned = useMemo(
    () => (graph ? layout(graph.nodes, graph.edges) : []),
    [graph],
  );

  const neighbors = useMemo(() => {
    if (!graph || !selectedNode) return new Set<string>();
    const set = new Set<string>([selectedNode]);
    for (const e of graph.edges) {
      if (e.source === selectedNode) set.add(e.target);
      if (e.target === selectedNode) set.add(e.source);
    }
    return set;
  }, [graph, selectedNode]);

  const selectedNodeData = positioned.find((n) => n.id === selectedNode);
  const selectedEdges = graph?.edges.filter(
    (e) => e.source === selectedNode || e.target === selectedNode,
  );

  return (
    <div className="mx-auto max-w-7xl px-8 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight">
            <Network className="size-6 text-cyan" />
            Knowledge Graph
          </h1>
          <p className="mt-1 text-sm text-muted">
            Evidence network linking patient, variants, genes, diseases, phenotypes, drugs and
            guidelines. Click any node to trace its connections.
          </p>
        </div>
        <div className="flex gap-2">
          {patientIds.map((pt) => (
            <button
              key={pt.id}
              onClick={() => setSelectedPatient(pt.id)}
              className={`rounded-lg border px-4 py-2 text-sm font-semibold transition-all ${
                pt.id === selectedPatient
                  ? "border-cyan/50 bg-cyan/10 text-cyan"
                  : "border-navy-950/10 text-muted hover:border-navy-950/25"
              }`}
            >
              {pt.identifier}
            </button>
          ))}
        </div>
      </header>

      {error && <p className="text-sm text-error">Unable to load knowledge graph. Check that you are signed in and the backend is running.</p>}
      {!error && patientIds.length === 0 && (
        <p className="text-sm text-muted">No persisted patients yet. Complete Clinical Workup to generate a graph.</p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
        <section className="card card-glow-cyan relative overflow-hidden">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" onClick={() => setSelectedNode(null)}>
            {/* Edges */}
            {graph &&
              positioned.length > 0 &&
              graph.edges.map((e, i) => {
                const a = positioned.find((n) => n.id === e.source);
                const b = positioned.find((n) => n.id === e.target);
                if (!a || !b) return null;
                const active =
                  selectedNode !== null && (e.source === selectedNode || e.target === selectedNode);
                const dimmed = selectedNode !== null && !active;
                return (
                  <g key={i}>
                    <line
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke={active ? "#b4182d" : "rgba(55,65,92,0.25)"}
                      strokeWidth={active ? 2 : 1}
                      opacity={dimmed ? 0.15 : 1}
                    />
                    {active && (
                      <text
                        x={(a.x + b.x) / 2}
                        y={(a.y + b.y) / 2 - 5}
                        textAnchor="middle"
                        className="mono"
                        fontSize={9}
                        fill="#b4182d"
                      >
                        {e.relation}
                      </text>
                    )}
                  </g>
                );
              })}

            {/* Nodes */}
            {positioned.map((n, i) => {
              const style = NODE_STYLE[n.type] ?? NODE_STYLE.evidence;
              const isSelected = n.id === selectedNode;
              const isNeighbor = neighbors.has(n.id);
              const dimmed = selectedNode !== null && !isNeighbor;
              return (
                <motion.g
                  key={n.id}
                  initial={{ opacity: 0, scale: 0 }}
                  animate={{ opacity: dimmed ? 0.2 : 1, scale: 1 }}
                  transition={{ delay: Math.min(i * 0.03, 0.8), type: "spring", stiffness: 200, damping: 18 }}
                  style={{ cursor: "pointer", transformOrigin: `${n.x}px ${n.y}px` }}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setSelectedNode(isSelected ? null : n.id);
                  }}
                >
                  {isSelected && (
                    <circle cx={n.x} cy={n.y} r={style.r + 8} fill="none" stroke={style.color} strokeWidth={1.5} opacity={0.5} className="pulse-glow" />
                  )}
                  <circle
                    cx={n.x}
                    cy={n.y}
                    r={style.r}
                    fill={`${style.color}22`}
                    stroke={style.color}
                    strokeWidth={isSelected || isNeighbor ? 2 : 1.2}
                    style={isSelected ? { filter: `drop-shadow(0 0 8px ${style.color})` } : undefined}
                  />
                  <text
                    x={n.x}
                    y={n.y + style.r + 13}
                    textAnchor="middle"
                    fontSize={10}
                    fontWeight={600}
                    fill={dimmed ? "rgba(55,65,92,0.4)" : "#f8fafc"}
                  >
                    {n.label.length > 26 ? n.label.slice(0, 24) + "…" : n.label}
                  </text>
                  {n.sublabel && (isSelected || n.type === "patient") && (
                    <text x={n.x} y={n.y + style.r + 25} textAnchor="middle" fontSize={8} fill="#94a3b8">
                      {n.sublabel.length > 30 ? n.sublabel.slice(0, 28) + "…" : n.sublabel}
                    </text>
                  )}
                </motion.g>
              );
            })}
          </svg>

          {/* Legend */}
          <div className="glass absolute bottom-3 left-3 flex flex-wrap gap-x-4 gap-y-1 rounded-xl px-4 py-2.5">
            {Object.entries(NODE_STYLE).map(([k, s]) => (
              <span key={k} className="flex items-center gap-1.5 text-[10px] text-muted">
                <span className="size-2.5 rounded-full" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        </section>

        {/* Detail panel */}
        <aside className="card h-fit p-5">
          {selectedNodeData ? (
            <motion.div key={selectedNodeData.id} initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }}>
              <div className="flex items-start justify-between">
                <span
                  className="rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
                  style={{
                    color: (NODE_STYLE[selectedNodeData.type] ?? NODE_STYLE.evidence).color,
                    background: `${(NODE_STYLE[selectedNodeData.type] ?? NODE_STYLE.evidence).color}1a`,
                  }}
                >
                  {selectedNodeData.type}
                </span>
                <button onClick={() => setSelectedNode(null)} className="text-muted hover:text-fg">
                  <X className="size-4" />
                </button>
              </div>
              <p className="mt-2 text-lg font-bold leading-tight">{selectedNodeData.label}</p>
              {selectedNodeData.sublabel && (
                <p className="mono mt-1 text-xs text-muted">{selectedNodeData.sublabel}</p>
              )}
              <h4 className="mt-5 mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted">
                Connections ({selectedEdges?.length ?? 0})
              </h4>
              <ul className="space-y-1.5">
                {selectedEdges?.map((e, i) => {
                  const otherId = e.source === selectedNode ? e.target : e.source;
                  const other = positioned.find((n) => n.id === otherId);
                  return (
                    <li key={i}>
                      <button
                        onClick={() => setSelectedNode(otherId)}
                        className="w-full rounded-lg border border-navy-950/8 bg-panel2 px-3 py-2 text-left text-xs transition-colors hover:border-cyan/40"
                      >
                        <span className="text-muted">{e.relation} → </span>
                        <span className="font-medium">{other?.label}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </motion.div>
          ) : (
            <div className="py-10 text-center text-sm text-muted">
              <Network className="mx-auto mb-3 size-8 opacity-40" />
              Select a node to inspect its
              <br />
              evidence connections.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
