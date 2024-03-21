import argparse
import gzip

parser = argparse.ArgumentParser(
    description="Reads the VCF file, parses multi-allelic variants into multiple lines, and filters out variants under the MAF threshold."
)

parser.add_argument("-i", dest="input_file", required=True, help="input VCF")

parser.add_argument(
    "-af_field",
    dest="af_field",
    required=False,
    type=str,
    help='Allele Frequency (AF) field name - default "AF"',
    default="AF",
)

parser.add_argument(
    "-af",
    dest="min_af",
    required=False,
    type=float,
    help="Allele Frequency (AF) lower threshold - default 0",
    default=0,
)

parser.add_argument(
    "-chr",
    dest="chromosome",
    required=True,
    help="chromosome being processed (e.g., 1, 12 or X)",
)

parser.add_argument("-o", dest="output_file", required=True, help="output VCF")

args = parser.parse_args()


def get_MAF(info):
    if ";" + args.af_field + "=" in info:
        return info.split(";" + args.af_field + "=")[1].split(";")[0]
    elif "\t" + args.af_field + "=" in info:
        return info.split("\t" + args.af_field + "=")[1].split(";")[0]

    return "-1"


# read the header of the VCF - keep only the last line of the header
VCF_header = ""

vcf_file = gzip.open(args.input_file, "rt")  # open(args.input_file, 'r')
outfile = open(args.output_file, "w")

line = next(vcf_file)  # .readline()

while line != "" and line.startswith("#"):
    VCF_header += line
    line = next(vcf_file)  # .readline()

outfile.write(VCF_header)

# check if the VCF has any valid lines
if line == "":
    outfile.close()
    vcf_file.close()
    print("VCF file is empty!")
    exit()

total_VCF_entries = 0
valid_VCF_entries = 0

while line != "":
    ALT = line.split(maxsplit=5)[4]
    INFO = line.split(maxsplit=8)[7]
    MAF = get_MAF(INFO)
    total_VCF_entries += 1

    new_line = ""
    if "," in ALT:
        CHR = line.split(maxsplit=1)[0]
        POS = line.split(maxsplit=1)[0]
        ID = line.split(maxsplit=1)[0]
        REF = line.split(maxsplit=1)[0]

        for i, allele in enumerate(ALT.split(",")):
            allele_maf = float(MAF.split(",")[i])

            if allele_maf >= args.min_af:
                invalid_gts = list(range(1, 100))
                invalid_gts.remove(i + 1)
                GTs = line.split(maxsplit=9)[-1]
                for gt_id in invalid_gts:
                    GTs = GTs.replace(str(gt_id) + "|", "0|")
                    GTs = GTs.replace("|" + str(gt_id), "|0")

                GTs = GTs.replace(str(i + 1) + "|", "1|")
                GTs = GTs.replace("|" + str(i + 1), "|1")

                new_line += "\t".join(
                    line.split(maxsplit=4)[:-1]
                    + [allele]
                    + line.split(maxsplit=7)[5:-1]
                )
                new_line += "\tMAF=" + str(allele_maf) + "\tGT\t" + GTs
                valid_VCF_entries += 1

    else:
        allele_maf = float(MAF)
        if allele_maf >= args.min_af:
            new_line = line
            valid_VCF_entries += 1

    outfile.write(new_line)

    line = vcf_file.readline()
    # line = next(vcf_file)

vcf_file.close()
outfile.close()

print(("Chr " + args.chromosome + ":"), "Original VCF:", total_VCF_entries, "lines")
print(("Chr " + args.chromosome + ":"), "Filtered VCF:", valid_VCF_entries, "lines")
