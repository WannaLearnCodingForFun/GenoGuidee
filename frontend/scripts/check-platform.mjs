#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const src = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src");
const fail = [];

function exists(rel) {
  if (!fs.existsSync(path.join(src, rel))) fail.push(`missing ${rel}`);
}

[
  "app/(app)/dashboard/page.tsx",
  "app/(app)/evidence-intelligence/page.tsx",
  "app/(app)/reanalysis/page.tsx",
  "app/(app)/curation/page.tsx",
  "app/(app)/phenotype-analysis/page.tsx",
  "app/(app)/inheritance/page.tsx",
  "app/(app)/acmg-simulator/page.tsx",
  "app/(app)/phenopackets/page.tsx",
  "app/(app)/model-monitoring/page.tsx",
  "app/(app)/interpretations/[id]/page.tsx",
  "lib/api.ts",
  "lib/platform/client.ts",
  "lib/platform/types.ts",
  "lib/nav.ts",
  "components/Sidebar.tsx",
  "components/AuthGate.tsx",
].forEach(exists);

if (!fs.existsSync(path.join(src, "app/(auth)/login/page.tsx"))) fail.push("missing auth login");

const nav = fs.readFileSync(path.join(src, "lib/nav.ts"), "utf8");
for (const href of ["/dashboard", "/clinical-workup", "/variant-lab", "/knowledge-graph", "/provenance"]) {
  if (!nav.includes(href)) fail.push(`nav missing ${href}`);
}
const plat = fs.readFileSync(path.join(src, "lib/platformNav.ts"), "utf8");
for (const href of ["/evidence-intelligence", "/reanalysis", "/curation"]) {
  if (!plat.includes(href)) fail.push(`platform nav missing ${href}`);
}
const auth = fs.readFileSync(path.join(src, "components/AuthGate.tsx"), "utf8");
if (!auth.includes("/evidence-intelligence")) fail.push("AuthGate missing platform prefixes");
const kg = fs.readFileSync(path.join(src, "app/(app)/knowledge-graph/page.tsx"), "utf8");
if (!kg.includes("Open Evidence Intelligence")) fail.push("KG missing additive link");
if (kg.includes('href="/evidence-graph"')) fail.push("KG replaced by /evidence-graph");

if (fail.length) {
  console.error(fail.join("\n"));
  process.exit(1);
}
console.log("frontend platform route checks PASS");
