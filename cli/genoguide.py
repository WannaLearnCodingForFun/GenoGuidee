"""
GenoGuide terminal interface.

    python -m cli.genoguide <command> [args]

Commands:
    status                       engine/component/data status
    data list|download|verify    dataset acquisition (manifest-driven)
    validate-vcf FILE            VCF validation report
    normalize-vcf FILE           trim + decompose multiallelics (+bcftools if present)
    annotate FILE                annotate a VCF against available evidence sources
    interpret --variant SPEC     interpret one variant (build:chrom:pos:ref>alt)
    interpret-vcf FILE           interpret all variants in a VCF
    acmg FILE.json               run ACMG v2 on an evidence JSON
    phenotype FILE.json          phenotype matching for a patient JSON
    graph GENE                   gene-centric knowledge graph
    train --config FILE          train models on the research dataset
    benchmark [--all]            benchmark models across splits
    leakage                      run the split leakage audit
    provenance verify ID         verify an interpretation on the ledger
    demo                         guaranteed terminal showcase (BRCA1/TP53/CFTR)
    pipeline --vcf F --patient P end-to-end interpretation pipeline
"""
from __future__ import annotations

import argparse
import json
import sys

import cli  # noqa: F401  (sys.path bootstrap)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="genoguide", description="GenoGuide research engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status")

    p_data = sub.add_parser("data")
    p_data.add_argument("action", choices=["list", "download", "verify"])
    p_data.add_argument("dataset", nargs="?")
    p_data.add_argument("--force", action="store_true")

    for name in ("validate-vcf", "normalize-vcf", "annotate", "interpret-vcf"):
        p = sub.add_parser(name)
        p.add_argument("vcf")
        p.add_argument("--build", default="GRCh38", choices=["GRCh38", "GRCh37"])
        p.add_argument("--output", default=None)

    p_int = sub.add_parser("interpret")
    p_int.add_argument("--variant", required=True, help="build:chrom:pos:ref>alt e.g. GRCh38:17:43057062:T>TG")
    p_int.add_argument("--gene", default=None)
    p_int.add_argument("--consequence", default=None)
    p_int.add_argument("--patient", default=None, help="patient JSON file with hpo_terms")

    p_acmg = sub.add_parser("acmg")
    p_acmg.add_argument("evidence_json")

    p_phen = sub.add_parser("phenotype")
    p_phen.add_argument("patient_json")
    p_phen.add_argument("--top", type=int, default=10)

    p_graph = sub.add_parser("graph")
    p_graph.add_argument("gene")

    p_fam = sub.add_parser("family")
    p_fam.add_argument("family_json")

    p_res = sub.add_parser("research")
    p_res.add_argument("action", choices=["run"])
    p_res.add_argument("--config", default="configs/research_full.yaml")
    p_res.add_argument("--train", action="store_true")

    p_train = sub.add_parser("train")
    p_train.add_argument("--config", default="configs/model.yaml")

    p_bench = sub.add_parser("benchmark")
    p_bench.add_argument("--all", action="store_true")
    p_bench.add_argument("--splits", default="random,gene_disjoint,chromosome_disjoint,temporal")
    p_bench.add_argument("--config", default="configs/model.yaml")

    sub.add_parser("leakage")

    p_prov = sub.add_parser("provenance")
    p_prov.add_argument("action", choices=["verify", "audit"])
    p_prov.add_argument("id", nargs="?")

    sub.add_parser("demo")

    p_pipe = sub.add_parser("pipeline")
    p_pipe.add_argument("--vcf", required=True)
    p_pipe.add_argument("--patient", default=None)
    p_pipe.add_argument("--output", default="results")
    p_pipe.add_argument("--build", default="GRCh38", choices=["GRCh38", "GRCh37"])

    args = parser.parse_args(argv)

    if args.command == "status":
        from cli.commands import status_cmd
        return status_cmd.run()
    if args.command == "data":
        from cli.commands import data_cmd
        return data_cmd.run(args)
    if args.command in ("validate-vcf", "normalize-vcf", "annotate", "interpret-vcf"):
        from cli.commands import vcf_cmd
        return vcf_cmd.run(args.command, args)
    if args.command == "interpret":
        from cli.commands import interpret_cmd
        return interpret_cmd.run(args)
    if args.command == "acmg":
        from cli.commands import acmg_cmd
        return acmg_cmd.run(args)
    if args.command == "phenotype":
        from cli.commands import phenotype_cmd
        return phenotype_cmd.run(args)
    if args.command == "graph":
        from cli.commands import graph_cmd
        return graph_cmd.run(args)
    if args.command == "family":
        from cli.commands import family_cmd
        return family_cmd.run(args)
    if args.command == "research":
        from cli.commands import research_cmd
        return research_cmd.run(args)
    if args.command == "train":
        from cli.commands import train_cmd
        return train_cmd.run(args)
    if args.command == "benchmark":
        from cli.commands import benchmark_cmd
        return benchmark_cmd.run(args)
    if args.command == "leakage":
        from cli.commands import leakage_cmd
        return leakage_cmd.run()
    if args.command == "provenance":
        from cli.commands import provenance_cmd
        return provenance_cmd.run(args)
    if args.command == "demo":
        from cli.commands import demo_cmd
        return demo_cmd.run()
    if args.command == "pipeline":
        from cli.commands import pipeline_cmd
        return pipeline_cmd.run(args)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
