# scripts/fetch_1000g_trio_regions.sh
# Run in WSL / Git-Bash / a shell with tabix installed.

mkdir -p data/raw/trio_regions
BASE="http://ftp.1000genomes.org/vol1/ftp/release/20130502"

# gene: chrom  start        end          (GRCh37, padded ~2kb)
declare -A REGIONS=(
  [CFTR]="7:117118000-117312000"
  [HBB]="11:5246000-5250000"
  [GJB2]="13:20760000-20765000"
  [PAH]="12:102836000-102958000"
)

for gene in "${!REGIONS[@]}"; do
  chrom="${REGIONS[$gene]%%:*}"
  region="${REGIONS[$gene]}"
  vcf="$BASE/ALL.chr${chrom}.phase3_shapeit2_mvncall_integrated_v5a.20130502.genotypes.vcf.gz"
  echo "Fetching $gene ($region) ..."
  tabix -h "$vcf" "$region" > "data/raw/trio_regions/${gene}.vcf"
done

echo "Done. Region VCFs in data/raw/trio_regions/"