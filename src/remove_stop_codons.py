import argparse
import os.path
import re


parser = argparse.ArgumentParser(
    description="Reads a FASTA file, removes stop codons (*) and writes relative positions of the stop codons into the peptide header. E.g., if the sequence is PE*TI, it becomes PETI, and position 2 of a stop codon is written in the header."
)


def is_valid_file(parser, arg):
    if not os.path.exists(arg):
        parser.error("The file %s does not exist!" % arg)
    else:
        return open(arg, "r")  # return an open file handle


parser.add_argument(
    "-i",
    dest="input_file",
    required=True,
    help="input FASTA file",
    metavar="FILE",
    type=lambda x: is_valid_file(parser, x),
)

parser.add_argument(
    "-min_len",
    dest="min_len",
    required=False,
    type=int,
    help="minimal length of a protein sequence; default: 1",
    default=1,
)

parser.add_argument(
    "-o",
    dest="output_file",
    required=True,
    help="output FASTA file",
    metavar="FILE",
    type=lambda x: open(x, "w"),
)

args = parser.parse_args()

print("")
print("Reading file", args.input_file.name)
print("Removing stop codons (*).")

metadata = args.input_file.readline()  # line starting with '>'
sequence = ""  # all the other lines are considered protein sequences (considering also a multi-line format)

while metadata != "":

    line = args.input_file.readline()
    while not line.startswith(">") and not line == "":
        sequence += line[:-1]
        line = args.input_file.readline()

    tag, accession, description = metadata.split("|")

    if "start:" in description:
        start_pos = int(description.split("start:", 1)[1].split(" ", 1)[0])
    else:
        start_pos = 0

    if ("*" in sequence) or (start_pos > 0):

        positions = [0] + [
            m.start() + 1
            for m in re.finditer("\*", sequence)
            if ((m.start() + 1) < len(sequence))
        ]  # remember the positions of stop codons, but ignore if the stop codon is the last letter in the sequence
        protein_fragments = []

        # start codon position available -> split into 5'UTR, 3'UTR and mORF
        if start_pos > 0:
            protein_fragments = sequence[:start_pos].split(
                "*"
            )  # add all parts of the 5'UTR translation
            main_protein = sequence[start_pos:].split("*", 1)[
                0
            ]  # add the main protein sequence

            # add all parts of the 3'UTR translation, if any
            if start_pos + len(main_protein) + 1 < len(sequence):
                UTR_sequences = sequence[start_pos + len(main_protein) + 1 :].split("*")

                # if the protein ends with a stop codon sign, don't add the last empty sequence
                if len(UTR_sequences[-1]) == 0:
                    UTR_sequences = UTR_sequences[:-1]
                protein_fragments.extend(UTR_sequences)

            positions.append(start_pos)
            protein_fragments.append(main_protein)

        # start codon position unknown or 0 -> assume the sequence until the first stop codon is the mORF, mark everything else as UTR
        else:
            protein_fragments = sequence.split("*")

            # if the protein ends with a stop codon sign, don't add the last empty sequence
            if len(protein_fragments[-1]) == 0:
                protein_fragments = protein_fragments[:-1]

        # write all the subsequences as separate fasta entries
        for i, fragment in enumerate(protein_fragments):
            if len(fragment) >= args.min_len:
                new_acc = accession

                if positions[i] < start_pos:
                    new_acc += "_5UTR_" + str(i)
                elif positions[i] > start_pos:
                    new_acc += "_3UTR_" + str(i)

                args.output_file.write(
                    tag
                    + "|"
                    + new_acc
                    + "|"
                    + "position_within_protein:"
                    + str(positions[i])
                    + " "
                    + description
                )
                if fragment.endswith("\n"):
                    args.output_file.write(fragment)
                else:
                    args.output_file.write(fragment + "\n")

        # sequence = sequence.replace('*', '')   # remove the stop codons
        # metadata = metadata[:-1] + " stop:" + ".".join(str(x) for x in positions) + '\n'

    # no stop codon in the sequence, start codon at position 0 -> do nothing
    elif len(sequence) >= args.min_len:
        args.output_file.write(
            tag + "|" + accession + "|position_within_protein:0 " + description
        )  # if non-empty, write the metadata line

        if sequence.endswith("\n"):
            args.output_file.write(sequence)
        else:
            args.output_file.write(sequence + "\n")

    metadata = line
    sequence = ""

args.output_file.close()
args.input_file.close()
print("Done")
