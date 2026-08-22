# scripts/check_cftr.py
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "data" / "raw" / "trio_regions" / "CFTR.vcf"

with open(path, encoding="utf-8") as f:
    lines = f.readlines()

print("total lines:", len(lines))
data_lines = [l for l in lines if not l.startswith("#")]
print("data lines:", len(data_lines))
print()
print("first data line:")
print(repr(data_lines[0][:300]))
print()
bad = sum(l.count(chr(0xFFFD)) for l in data_lines)
print("replacement char count:", bad)