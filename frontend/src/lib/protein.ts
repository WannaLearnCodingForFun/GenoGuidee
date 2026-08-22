const AA3: Record<string, string> = {
  ALA: "A", ARG: "R", ASN: "N", ASP: "D", CYS: "C",
  GLN: "Q", GLU: "E", GLY: "G", HIS: "H", ILE: "I",
  LEU: "L", LYS: "K", MET: "M", PHE: "F", PRO: "P",
  SER: "S", THR: "T", TRP: "W", TYR: "Y", VAL: "V",
  TER: "*", TRM: "*", STOP: "*",
};

/** Map p.Val600Glu / V600E → V600E. Returns null for genomic / c. HGVS. */
export function mapProteinChange(value: string | null | undefined): string | null {
  if (!value) return null;
  let s = value.trim();
  if (!s) return null;
  if (/^GRCH/i.test(s) || /^c\./i.test(s) || /:\d+:/.test(s)) return null;
  if (/fs|del|ins|dup|delins/i.test(s.replace(/^p\./i, ""))) return null;
  if (s.includes(":p.")) s = `p.${s.split(":p.")[1]}`;
  const hgvs = /p\.([A-Za-z]{3})(\d+)([A-Za-z]{3}|\*)/i.exec(s);
  if (hgvs) {
    const ref = AA3[hgvs[1].toUpperCase()];
    const alt = hgvs[3] === "*" ? "*" : AA3[hgvs[3].toUpperCase()];
    if (ref && alt) return `${ref}${hgvs[2]}${alt}`;
    return null;
  }
  const bare = /^(?:p\.)?([A-Z*])(\d+)([A-Z*])$/i.exec(s);
  if (bare) return `${bare[1].toUpperCase()}${bare[2]}${bare[3].toUpperCase()}`;
  return null;
}
