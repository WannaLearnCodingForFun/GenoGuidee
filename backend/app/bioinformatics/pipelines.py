"""
WES/WGS pipeline wrappers (RESEARCH PIPELINE — explicitly not a clinical
diagnostic pipeline).

These are execution wrappers around established tools:

    FASTQ → FastQC → MultiQC → BWA-MEM2 → samtools sort/index →
    duplicate marking → variant calling (DeepVariant primary,
    GATK HaplotypeCaller optional) → VCF

Design constraints honored here:
  * No tool is required just to run variant interpretation — interpretation
    consumes VCFs; this module is optional.
  * Nothing is faked: if a tool is not installed, the step reports
    NOT_INSTALLED and the plan shows the exact command that would run.
  * Every step produces a log path and a machine-readable step report.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PIPELINE_CLASS = "RESEARCH_PIPELINE"  # never claim clinical-grade validation

TOOLS = {
    "fastqc": ["fastqc", "--version"],
    "multiqc": ["multiqc", "--version"],
    "bwa-mem2": ["bwa-mem2", "version"],
    "samtools": ["samtools", "--version"],
    "gatk": ["gatk", "--version"],
    "deepvariant": ["run_deepvariant", "--version"],  # typically via docker
    "docker": ["docker", "--version"],
    "bcftools": ["bcftools", "--version"],
}


def tool_status() -> dict[str, dict[str, Any]]:
    out = {}
    for name, probe in TOOLS.items():
        path = shutil.which(probe[0])
        version = None
        if path:
            try:
                r = subprocess.run(probe, capture_output=True, text=True, timeout=20)
                version = (r.stdout or r.stderr).strip().splitlines()[0][:80]
            except Exception:  # noqa: BLE001
                version = "installed (version probe failed)"
        out[name] = {"installed": path is not None, "path": path, "version": version}
    return out


@dataclass
class Step:
    name: str
    tool: str
    command: list[str]
    outputs: list[str] = field(default_factory=list)


def build_germline_plan(
    fastq_r1: str,
    fastq_r2: str | None,
    reference_fasta: str,
    sample: str,
    outdir: str,
    caller: str = "deepvariant",
) -> list[Step]:
    """Construct the exact commands of the research germline pipeline."""
    out = Path(outdir)
    fq = [fastq_r1] + ([fastq_r2] if fastq_r2 else [])
    bam = str(out / f"{sample}.sorted.bam")
    mkdup = str(out / f"{sample}.mkdup.bam")
    vcf = str(out / f"{sample}.{caller}.vcf.gz")

    steps = [
        Step("qc", "fastqc", ["fastqc", "-o", str(out / "qc"), *fq],
             [str(out / "qc")]),
        Step("qc-aggregate", "multiqc", ["multiqc", "-o", str(out / "qc"), str(out / "qc")],
             [str(out / "qc" / "multiqc_report.html")]),
        Step("align", "bwa-mem2",
             ["bash", "-c",
              f"bwa-mem2 mem -t 8 -R '@RG\\tID:{sample}\\tSM:{sample}\\tPL:ILLUMINA' "
              f"{reference_fasta} {' '.join(fq)} | samtools sort -@4 -o {bam} - "
              f"&& samtools index {bam}"],
             [bam]),
        Step("mark-duplicates", "samtools",
             ["bash", "-c",
              f"samtools collate -@4 -O {bam} - | samtools fixmate -m - - | "
              f"samtools sort -@4 - | samtools markdup - {mkdup} && samtools index {mkdup}"],
             [mkdup]),
    ]
    if caller == "deepvariant":
        steps.append(Step(
            "call-variants", "deepvariant",
            ["run_deepvariant", "--model_type=WGS", f"--ref={reference_fasta}",
             f"--reads={mkdup}", f"--output_vcf={vcf}", "--num_shards=8"],
            [vcf]))
    else:
        # BQSR belongs to the GATK path; requires known-sites resources.
        steps.append(Step(
            "call-variants", "gatk",
            ["gatk", "HaplotypeCaller", "-R", reference_fasta, "-I", mkdup, "-O", vcf],
            [vcf]))
    return steps


def run_plan(steps: list[Step], outdir: str, execute: bool = False) -> dict[str, Any]:
    """Dry-run by default. With execute=True, runs each step whose tool is
    installed; stops at the first failure. Never fabricates outputs."""
    out = Path(outdir)
    (out / "logs").mkdir(parents=True, exist_ok=True)
    status = tool_status()
    report: dict[str, Any] = {
        "pipeline_class": PIPELINE_CLASS,
        "executed": execute,
        "steps": [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    for step in steps:
        entry: dict[str, Any] = {
            "step": step.name, "tool": step.tool,
            "command": " ".join(step.command),
            "tool_installed": status.get(step.tool, {}).get("installed", False),
        }
        if not execute:
            entry["state"] = "PLANNED" if entry["tool_installed"] else "NOT_INSTALLED"
        elif not entry["tool_installed"]:
            entry["state"] = "NOT_INSTALLED"
            report["steps"].append(entry)
            report["stopped_at"] = step.name
            break
        else:
            log = out / "logs" / f"{step.name}.log"
            with open(log, "w") as lf:
                r = subprocess.run(step.command, stdout=lf, stderr=subprocess.STDOUT)
            entry["state"] = "OK" if r.returncode == 0 else "FAILED"
            entry["log"] = str(log)
            entry["returncode"] = r.returncode
            if r.returncode != 0:
                report["steps"].append(entry)
                report["stopped_at"] = step.name
                break
        report["steps"].append(entry)
    return report
