/**
 * VCF 4.x parser.
 *
 * Normalizes uploaded variant records onto the exact annotation shape the
 * backend ACMG rule engine (`acmg.py`) and the XGBoost feature builder
 * (`ml.py`) already consume: consequence, gnomad_af, cadd, revel, spliceai,
 * phylop, plus gene/transcript/HGVS for display.
 *
 * Annotations are read from three places, in priority order:
 *   1. VEP  `CSQ=`  — field order taken from the ##INFO header Format string
 *   2. SnpEff `ANN=` — fixed field order per the SnpEff spec
 *   3. Flat INFO keys (CADD_PHRED=, REVEL=, gnomAD_AF=, …) with common aliases
 *
 * A plain unannotated VCF still parses; it simply yields null scores, which
 * the UI reports as low annotation completeness.
 */

export interface ParsedVariant {
  line_number: number;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene: string | null;
  transcript: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  consequence: string | null;
  gnomad_af: number | null;
  cadd: number | null;
  revel: number | null;
  spliceai: number | null;
  phylop: number | null;
  qual: number | null;
  filter: string | null;
}

export interface ParseResult {
  variants: ParsedVariant[];
  totalRecords: number;
  skipped: number;
  annotatedCount: number;
  referenceGenome: string | null;
  annotationSource: "VEP (CSQ)" | "SnpEff (ANN)" | "INFO fields" | "none";
  errors: string[];
  truncated: boolean;
}

/** Hard ceiling so a whole-genome VCF cannot lock up the browser tab. */
export const MAX_VARIANTS = 5000;
export const MAX_FILE_BYTES = 50 * 1024 * 1024;

/**
 * SO term -> the internal vocabulary used by `_CONSEQUENCE_RANK` in ml.py and
 * `NULL_CONSEQUENCES` in acmg.py. Ordered most severe first; when a record
 * carries several `&`-joined terms the most severe one wins.
 */
const CONSEQUENCE_MAP: [string, string][] = [
  ["transcript_ablation", "nonsense"],
  ["frameshift_variant", "frameshift"],
  ["stop_gained", "nonsense"],
  ["start_lost", "nonsense"],
  ["stop_lost", "nonsense"],
  ["splice_acceptor_variant", "splice_acceptor"],
  ["splice_donor_variant", "splice_donor"],
  ["inframe_deletion", "inframe_deletion"],
  ["inframe_insertion", "inframe_deletion"],
  ["protein_altering_variant", "missense"],
  ["missense_variant", "missense"],
  ["stop_retained_variant", "synonymous"],
  ["synonymous_variant", "synonymous"],
  ["splice_region_variant", "intronic"],
  ["intron_variant", "intronic"],
  ["5_prime_UTR_variant", "intronic"],
  ["3_prime_UTR_variant", "intronic"],
  ["upstream_gene_variant", "intronic"],
  ["downstream_gene_variant", "intronic"],
  ["intergenic_variant", "intronic"],
  ["non_coding_transcript_exon_variant", "intronic"],
];

const SEVERITY_ORDER = CONSEQUENCE_MAP.map(([so]) => so);

function mapConsequence(raw: string | null): string | null {
  if (!raw) return null;
  const terms = raw.split(/[&,]/).map((t) => t.trim().toLowerCase()).filter(Boolean);
  if (!terms.length) return null;
  let best: string | null = null;
  let bestRank = Number.MAX_SAFE_INTEGER;
  for (const term of terms) {
    const rank = SEVERITY_ORDER.indexOf(term);
    if (rank !== -1 && rank < bestRank) {
      bestRank = rank;
      best = CONSEQUENCE_MAP[rank][1];
    }
  }
  // An unrecognized term is still a real consequence — fall back to the
  // non-coding bucket rather than dropping the variant.
  return best ?? "intronic";
}

function toNumber(raw: string | null | undefined): number | null {
  if (raw === null || raw === undefined) return null;
  const s = raw.trim();
  if (!s || s === "." || s === "NA" || s === "-") return null;
  // Some annotators emit "0.12&0.30" for multi-transcript values; take the max.
  if (s.includes("&")) {
    const parts = s.split("&").map((p) => toNumber(p)).filter((n): n is number => n !== null);
    return parts.length ? Math.max(...parts) : null;
  }
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/** Case-insensitive lookup across a list of candidate INFO keys. */
function pick(info: Map<string, string>, keys: string[]): string | null {
  for (const k of keys) {
    const v = info.get(k.toLowerCase());
    if (v !== undefined && v !== "" && v !== ".") return v;
  }
  return null;
}

const AF_KEYS = [
  "gnomad_af", "gnomadg_af", "gnomade_af", "gnomad_genomes_af", "gnomad_exomes_af",
  "gnomad4_af", "af_gnomad", "gnomadaf", "max_af", "popmax_af", "af_popmax",
];
const CADD_KEYS = ["cadd_phred", "caddphred", "cadd", "cadd_raw_phred"];
const REVEL_KEYS = ["revel", "revel_score", "revel_rankscore"];
const PHYLOP_KEYS = [
  "phylop", "phylop100way_vertebrate", "phylop470way_mammalian",
  "phylop_score", "phylop100way",
];
const GENE_KEYS = ["symbol", "gene_name", "gene", "geneinfo", "genename"];

/** SpliceAI packs four delta scores into one pipe-joined value; take the max. */
function parseSpliceAi(info: Map<string, string>): number | null {
  const direct = pick(info, ["spliceai_max", "spliceai_ds_max", "ds_max"]);
  if (direct) return toNumber(direct);

  const raw = pick(info, ["spliceai", "spliceai_pred"]);
  if (raw) {
    // ALLELE|SYMBOL|DS_AG|DS_AL|DS_DG|DS_DL|DP_AG|DP_AL|DP_DG|DP_DL
    const parts = raw.split("|");
    const ds = parts.slice(2, 6).map((p) => toNumber(p)).filter((n): n is number => n !== null);
    if (ds.length) return Math.max(...ds);
  }

  const individual = ["ds_ag", "ds_al", "ds_dg", "ds_dl"]
    .map((k) => toNumber(info.get(k)))
    .filter((n): n is number => n !== null);
  return individual.length ? Math.max(...individual) : null;
}

/** "BRCA1:672" (GeneInfo) or a plain symbol. */
function cleanGene(raw: string | null): string | null {
  if (!raw) return null;
  const first = raw.split(/[|,]/)[0].trim();
  const symbol = first.includes(":") ? first.split(":")[0] : first;
  return symbol && symbol !== "." ? symbol.toUpperCase() : null;
}

function parseInfo(field: string): Map<string, string> {
  const map = new Map<string, string>();
  if (!field || field === ".") return map;
  for (const entry of field.split(";")) {
    if (!entry) continue;
    const eq = entry.indexOf("=");
    if (eq === -1) map.set(entry.toLowerCase(), "true");
    else map.set(entry.slice(0, eq).toLowerCase(), entry.slice(eq + 1));
  }
  return map;
}

/** Extract the pipe-separated field names from a ##INFO Format: "..." header. */
function csqFormatFromHeader(line: string): string[] | null {
  const m = line.match(/Format:\s*([^">]+)/i);
  if (!m) return null;
  return m[1].split("|").map((f) => f.trim().toLowerCase());
}

interface BlockAnnotation {
  gene: string | null;
  transcript: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  consequence: string | null;
  gnomad_af: number | null;
  cadd: number | null;
  revel: number | null;
  spliceai: number | null;
  phylop: number | null;
}

/** Read one VEP CSQ block using the header-declared field order. */
function readCsqBlock(values: string[], fields: string[]): BlockAnnotation {
  const at = (names: string[]): string | null => {
    for (const n of names) {
      const i = fields.indexOf(n);
      if (i !== -1 && values[i] !== undefined && values[i] !== "") return values[i];
    }
    return null;
  };
  return {
    gene: cleanGene(at(["symbol", "gene", "hgnc_symbol"])),
    transcript: at(["feature", "transcript_id", "feature_id"]),
    hgvs_c: at(["hgvsc", "hgvs_c"]),
    hgvs_p: at(["hgvsp", "hgvs_p"]),
    consequence: mapConsequence(at(["consequence", "annotation"])),
    gnomad_af: toNumber(at(["gnomad_af", "gnomadg_af", "gnomade_af", "max_af", "af"])),
    cadd: toNumber(at(["cadd_phred", "cadd"])),
    revel: toNumber(at(["revel", "revel_score"])),
    spliceai: toNumber(at(["spliceai_pred_ds_max", "spliceai_max", "spliceai"])),
    phylop: toNumber(at(["phylop", "phylop100way_vertebrate"])),
  };
}

/** SnpEff ANN has a fixed field order. */
function readAnnBlock(values: string[]): BlockAnnotation {
  return {
    gene: cleanGene(values[3] ?? null),
    transcript: values[6] ?? null,
    hgvs_c: values[9] ?? null,
    hgvs_p: values[10] ?? null,
    consequence: mapConsequence(values[1] ?? null),
    gnomad_af: null,
    cadd: null,
    revel: null,
    spliceai: null,
    phylop: null,
  };
}

/**
 * Pick the most informative annotation block. VEP/SnpEff emit one block per
 * transcript; we prefer the canonical one, else the most severe consequence.
 */
function chooseBlock(blocks: BlockAnnotation[], canonicalIdx: number): BlockAnnotation | null {
  if (!blocks.length) return null;
  if (canonicalIdx >= 0 && blocks[canonicalIdx]) return blocks[canonicalIdx];
  let best = blocks[0];
  let bestRank = Number.MAX_SAFE_INTEGER;
  for (const b of blocks) {
    const internal = b.consequence;
    const rank = internal
      ? CONSEQUENCE_MAP.findIndex(([, mapped]) => mapped === internal)
      : Number.MAX_SAFE_INTEGER;
    if (rank !== -1 && rank < bestRank) {
      bestRank = rank;
      best = b;
    }
  }
  return best;
}

export function parseVcf(text: string): ParseResult {
  const lines = text.split(/\r?\n/);
  const variants: ParsedVariant[] = [];
  const errors: string[] = [];

  let csqFields: string[] | null = null;
  let annPresent = false;
  let referenceGenome: string | null = null;
  let totalRecords = 0;
  let skipped = 0;
  let sawHeader = false;
  let truncated = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;

    if (line.startsWith("##")) {
      if (/^##INFO=<ID=CSQ/i.test(line)) csqFields = csqFormatFromHeader(line);
      if (/^##INFO=<ID=ANN/i.test(line)) annPresent = true;
      if (/^##reference=/i.test(line)) {
        const ref = line.slice(line.indexOf("=") + 1).trim();
        const base = ref.split(/[\\/]/).pop() ?? ref;
        // Strip a trailing .fa / .fasta / .fa.gz so the label reads "GRCh38".
        referenceGenome = base.replace(/\.(fa|fasta)(\.gz)?$/i, "");
      }
      if (!referenceGenome && /GRCh3[78]|hg19|hg38/i.test(line)) {
        referenceGenome = (line.match(/GRCh3[78]|hg19|hg38/i) ?? [])[0] ?? null;
      }
      continue;
    }

    if (line.startsWith("#CHROM")) {
      sawHeader = true;
      continue;
    }
    if (line.startsWith("#")) continue;

    const cols = line.split("\t");
    if (cols.length < 5) {
      // Tolerate space-delimited files that are otherwise well-formed.
      const alt = line.trim().split(/\s+/);
      if (alt.length < 5) {
        skipped++;
        if (errors.length < 10) errors.push(`Line ${i + 1}: fewer than 5 columns — skipped.`);
        continue;
      }
      cols.splice(0, cols.length, ...alt);
    }

    const [chromRaw, posRaw, , refAllele, altField] = cols;
    const pos = Number(posRaw);
    if (!Number.isFinite(pos)) {
      skipped++;
      if (errors.length < 10) errors.push(`Line ${i + 1}: POS "${posRaw}" is not a number — skipped.`);
      continue;
    }

    const qual = toNumber(cols[5]);
    const filter = cols[6] && cols[6] !== "." ? cols[6] : null;
    const info = parseInfo(cols[7] ?? "");

    // Flat INFO-level annotations, used as the fallback for every ALT.
    const flat: BlockAnnotation = {
      gene: cleanGene(pick(info, GENE_KEYS)),
      transcript: pick(info, ["feature", "transcript", "transcript_id"]),
      hgvs_c: pick(info, ["hgvsc", "hgvs_c"]),
      hgvs_p: pick(info, ["hgvsp", "hgvs_p"]),
      consequence: mapConsequence(pick(info, ["consequence", "csq_consequence", "effect", "most_severe_consequence"])),
      gnomad_af: toNumber(pick(info, AF_KEYS)),
      cadd: toNumber(pick(info, CADD_KEYS)),
      revel: toNumber(pick(info, REVEL_KEYS)),
      spliceai: parseSpliceAi(info),
      phylop: toNumber(pick(info, PHYLOP_KEYS)),
    };

    // Structured annotation blocks (one per transcript).
    let structured: BlockAnnotation | null = null;
    const csqRaw = info.get("csq");
    if (csqRaw && csqFields) {
      const blocks = csqRaw.split(",").map((b) => b.split("|"));
      const canonIdx = csqFields.indexOf("canonical");
      const canonical = canonIdx === -1 ? -1 : blocks.findIndex((b) => b[canonIdx] === "YES" || b[canonIdx] === "1");
      structured = chooseBlock(blocks.map((b) => readCsqBlock(b, csqFields!)), canonical);
    } else {
      const annRaw = info.get("ann");
      if (annRaw) {
        structured = chooseBlock(annRaw.split(",").map((b) => readAnnBlock(b.split("|"))), -1);
      }
    }

    // Structured wins field-by-field; flat INFO fills the gaps.
    const merged: BlockAnnotation = {
      gene: structured?.gene ?? flat.gene,
      transcript: structured?.transcript ?? flat.transcript,
      hgvs_c: structured?.hgvs_c ?? flat.hgvs_c,
      hgvs_p: structured?.hgvs_p ?? flat.hgvs_p,
      consequence: structured?.consequence ?? flat.consequence,
      gnomad_af: structured?.gnomad_af ?? flat.gnomad_af,
      cadd: structured?.cadd ?? flat.cadd,
      revel: structured?.revel ?? flat.revel,
      spliceai: structured?.spliceai ?? flat.spliceai,
      phylop: structured?.phylop ?? flat.phylop,
    };

    // One row per ALT allele — multi-allelic sites are split.
    for (const altAllele of (altField ?? ".").split(",")) {
      if (!altAllele || altAllele === ".") continue;
      totalRecords++;
      if (variants.length >= MAX_VARIANTS) {
        truncated = true;
        continue;
      }
      variants.push({
        line_number: i + 1,
        chrom: chromRaw.replace(/^chr/i, ""),
        pos,
        ref: refAllele,
        alt: altAllele,
        qual,
        filter,
        ...merged,
      });
    }
  }

  if (!sawHeader && !variants.length) {
    errors.unshift("No #CHROM header line and no parsable records — is this a VCF file?");
  }

  const annotatedCount = variants.filter(
    (v) => v.cadd !== null || v.revel !== null || v.spliceai !== null || v.phylop !== null,
  ).length;

  const annotationSource: ParseResult["annotationSource"] = csqFields
    ? "VEP (CSQ)"
    : annPresent
      ? "SnpEff (ANN)"
      : variants.some((v) => v.consequence !== null || v.cadd !== null || v.gnomad_af !== null)
        ? "INFO fields"
        : "none";

  return {
    variants,
    totalRecords,
    skipped,
    annotatedCount,
    referenceGenome,
    annotationSource,
    errors,
    truncated,
  };
}

/** Short human label for a parsed variant, e.g. "BRCA1 c.5266dupC" or "17:43057062 T>TG". */
export function variantLabel(v: {
  gene: string | null;
  hgvs_c: string | null;
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
}): string {
  if (v.gene && v.hgvs_c) return `${v.gene} ${v.hgvs_c}`;
  if (v.gene) return `${v.gene} ${v.chrom}:${v.pos}`;
  return `${v.chrom}:${v.pos} ${v.ref}>${v.alt}`;
}
