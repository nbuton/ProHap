import bisect
from modules.common import KeyWrapper
from io import StringIO
import pandas as pd
import re

global_list_of_lines = []


def check_vcf_line_validity(line, min_af, REF, ALT):
    # check the allele frequency
    # AF_pass = min_af <= 0
    # if ";AF=" in line:
    #     AF = float(line.split(";AF=")[1].split(";")[0].split(maxsplit=1)[0])
    #     AF_pass = AF >= min_af
    # elif ";MAF=" in line:
    #     AF = float(line.split(";MAF=")[1].split(";")[0].split(maxsplit=1)[0])
    #     AF_pass = AF >= min_af
    # elif "\tAF=" in line:
    #     AF = float(line.split("\tAF=")[1].split(";")[0].split(maxsplit=1)[0])
    #     AF_pass = AF >= min_af
    # elif "\tMAF=" in line:
    #     AF = float(line.split("\tMAF=")[1].split(";")[0].split(maxsplit=1)[0])
    #     AF_pass = AF >= min_af

    # check validity of alleles
    val_pass = True
    if (re.match(r"[CGTA]*[^CGTA]+[CGTA]*", REF) and REF != "-") or (
        re.match(r"[CGTA,]*[^CGTA,]+[CGTA,]*", ALT) and ALT != "-"
    ):
        val_pass = False

    return val_pass


def add_variants_to_transcripts(
    vcf_file_line,
    vcf_file,
    vcf_linecount,
    transcript_queue,
    current_pos,
    current_transcript,
    VCF_header,
    min_af,
    tmp_dir,
    finalize,
):

    # Process VCF lines
    while (current_pos < current_transcript.start or finalize) and vcf_file_line != "":
        REF, ALT = vcf_file_line.split(maxsplit=5)[3:5]
        valid = check_vcf_line_validity(vcf_file_line, min_af, REF, ALT)

        # check all transcripts in the queue
        if valid:
            vcf_id = vcf_file_line.split(maxsplit=3)[2]

            if vcf_id == ".":
                # add an identifier = line cound
                vcf_file_line = (
                    "\t".join(vcf_file_line.split(maxsplit=2)[:2])
                    + "\t"
                    + hex(vcf_linecount)[2:]
                    + "\t"
                    + vcf_file_line.split(maxsplit=3)[3]
                )

            for transcript_entry in transcript_queue:

                # check if the snp belongs to any of the exons
                for exon in transcript_entry["exons"]:
                    if exon.start < (current_pos + len(REF)):
                        if exon.end >= current_pos:
                            transcript_entry["file_content"] += vcf_file_line
                            break
                    else:
                        break  # exon starts after the mutation -> continue to another transcript

        vcf_linecount += 1
        try:
            vcf_file_line = get_next_line(vcf_file)  # .readline()
        except StopIteration:
            vcf_file_line = ""

        if vcf_file_line == "":
            break

        current_pos = int(vcf_file_line.split(maxsplit=2)[1])

    # remove passed transcripts from queue
    while len(transcript_queue) > 0 and (
        transcript_queue[0]["end"] < current_pos or finalize
    ):
        df = pd.read_csv(
            StringIO(VCF_header + transcript_queue[0]["file_content"]), sep="\t"
        )
        df.to_csv(
            tmp_dir + "/" + transcript_queue[0]["ID"] + ".tsv",
            sep="\t",
            index=False,
            header=True,
        )
        # result_dfs[transcript_queue[0]['ID']] = df
        transcript_queue.pop(0)

    return (
        VCF_header[:-1].split("\t"),
        vcf_file_line,
        vcf_linecount,
        transcript_queue,
        current_pos,
    )


def get_next_line(file):
    global global_list_of_lines
    if len(global_list_of_lines) != 0:
        return global_list_of_lines.pop(0)
    else:
        try:
            line_original_vcf = next(file)
            global_list_of_lines = preprocess_line(line_original_vcf)
            global_list_of_lines = [g for g in global_list_of_lines if g != ""]
            if len(global_list_of_lines) == 0:
                return ""
            return global_list_of_lines.pop(0)
        except:
            return ""


def preprocess_line(line):
    ALT = line.split(maxsplit=5)[4]
    INFO = line.split(maxsplit=8)[7]

    new_line = ""
    if "," in ALT:
        CHR = line.split(maxsplit=1)[0]
        POS = line.split(maxsplit=1)[0]
        ID = line.split(maxsplit=1)[0]
        REF = line.split(maxsplit=1)[0]

        for i, allele in enumerate(ALT.split(",")):
            invalid_gts = list(range(1, 100))
            invalid_gts.remove(i + 1)
            GTs = line.split(maxsplit=9)[-1]
            GTs = GTs.replace("/", "|")
            for gt_id in invalid_gts:
                GTs = GTs.replace(str(gt_id) + "|", "0|")
                GTs = GTs.replace("|" + str(gt_id), "|0")

            GTs = GTs.replace(str(i + 1) + "|", "1|")
            GTs = GTs.replace("|" + str(i + 1), "|1")

            new_line += "\t".join(
                line.split(maxsplit=4)[:-1] + [allele] + line.split(maxsplit=7)[5:-1]
            )
            new_line += "\tMAF=" + str(0.0) + "\tGT\t" + GTs

    else:
        new_line = line

    return new_line.split("\n")


# Process a VCF file, select rows that intersect exons of given transcripts. Results are written as TSV files in to a temporary folder. Returns a list of column names in the VCF.
# input:
# all_transcripts: list of GTF transcript features, ordered by start position
# vcf_file: file handle for reading the VCF
# annotations_db: FeatureDB of the GTF file
# min_af: threshold allele frequency (float)
def parse_vcf(all_transcripts, vcf_file, annotations_db, min_af, tmp_dir):
    if len(all_transcripts) == 0:
        raise RuntimeError("No transcript for this chromosome so this doesn't work")
    # read the header of the VCF - keep only the last line of the header
    VCF_header = ""

    vcf_linecount = 1
    line = next(vcf_file)  # .readline()

    while line != "" and line.startswith("#"):
        VCF_header = line[1:]
        vcf_linecount += 1
        line = next(vcf_file)  # vcf_file.readline()

    # check if the VCF has any valid lines
    if line == "":
        return []

    # browse the chromosome in a sweep-line approach - assumes that the VCF file is sorted!
    # keep a list of transcripts that intersect the current position of the sweep line -> assign the VCF line to all of these transcripts

    # TODO: get the coordinates within the transcript already here?

    transcript_queue = (
        []
    )  # queue of transcript objects inc. the exons, sorted by end position, each element aggregates the VCF file contents
    current_pos = int(line.split()[1])  # position of the current VCF entry
    # result_dfs = {}                     # a list of dataframes with VCF entries for each transcript, accessed by the stable transcript id

    last_transcript = None

    # iterate through all the transcripts - add the first one to the queue (and all others starting at the same location), and of each other, check if there is a gap that can be filled in by VCF entries
    # i.e., process all the VCF entries that lay before the current transcript -> update the queue
    for current_transcript in all_transcripts:

        if (last_transcript is not None) and (
            last_transcript.start < current_transcript.start
        ):

            colnames, line, vcf_linecount, transcript_queue, current_pos = (
                add_variants_to_transcripts(
                    line,
                    vcf_file,
                    vcf_linecount,
                    transcript_queue,
                    current_pos,
                    current_transcript,
                    VCF_header,
                    min_af,
                    tmp_dir,
                    False,
                )
            )

        # add the new transcript to the queue
        exons = [
            exon
            for exon in annotations_db.children(
                current_transcript, featuretype="exon", order_by="start"
            )
        ]
        queue_entry = {
            "transcript_obj": current_transcript,
            "ID": current_transcript.id,
            "exons": exons,
            "start": current_transcript.start,
            "end": current_transcript.end,
            "file_content": "",
        }
        nearest_idx = bisect.bisect_left(
            KeyWrapper(transcript_queue, key=lambda x: x["end"]), queue_entry["end"]
        )
        transcript_queue.insert(nearest_idx, queue_entry)

        last_transcript = current_transcript

    if len(all_transcripts) != 0:
        colnames, line, vcf_linecount, transcript_queue, current_pos = (
            add_variants_to_transcripts(
                line,
                vcf_file,
                vcf_linecount,
                transcript_queue,
                current_pos,
                current_transcript,
                VCF_header,
                min_af,
                tmp_dir,
                True,
            )
        )

    return colnames
