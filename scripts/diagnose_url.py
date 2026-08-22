# scripts/diagnose_url.py
import requests

url = "http://ftp.1000genomes.org/vol1/ftp/release/20130502/ALL.chr7.phase3_shapeit2_mvncall_integrated_v5a.20130502.genotypes.vcf.gz.tbi"

resp = requests.get(url, timeout=30, allow_redirects=True)
print("Final URL:", resp.url)
print("Status:", resp.status_code)
print("Content-Type:", resp.headers.get("Content-Type"))
print("Content-Encoding:", resp.headers.get("Content-Encoding"))
print("Content-Length:", resp.headers.get("Content-Length"))
print("First 100 bytes:", resp.content[:100])