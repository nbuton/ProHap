'''
Main file of the ProHap tool

Creates a database of CDS + protein haplotypes, and a fasta file of protein haplotype sequences.
'''

import gffutils
import argparse
import os.path
from vcf_reader import parse_vcf
from common import read_fasta
from get_haplotypes import get_gene_haplotypes
from process_haplotypes import process_store_haplotypes

parser = argparse.ArgumentParser(
        description='Creates a database of CDS + protein haplotypes, and a fasta file of protein haplotype sequences.')

def is_valid_file(parser, arg):
        if not os.path.exists(arg):
                parser.error("The file %s does not exist!" % arg)
        else:
                return open(arg, 'r')  # return an open file handle

parser.add_argument("-i", dest="input_vcf", required=True,
                    help="input VCF file", metavar="FILE",
                    type=lambda x: is_valid_file(parser, x))

parser.add_argument("-db", dest="annotation_db", required=True,
                    help="DB file created by gffutils from GTF")

parser.add_argument("-af", dest="min_af", required=False, type=float,
                    help="Allele Frequency (AF) lower threshold - default 0", default=0)

parser.add_argument("-cdna", dest="cdnas_fasta", required=True,
                    help="input cDNA fasta file")

parser.add_argument("-transcripts", dest="transcript_list", required=True,
                    help="list of transcript IDs, provided in a file", metavar="FILE",
                    type=lambda x: is_valid_file(parser, x))
                    
parser.add_argument("-foo", dest="min_foo", required=False, type=float,
                    help="Minimum FoO of a haplotype to be reported in the fasta", default=0)
                    
parser.add_argument("-tag", dest="fasta_tag", required=False,
                    help="tag for FASTa file entries", default='generic_enshap')

parser.add_argument("-id_prefix", dest="haplo_id_prefix", required=False,
                    help="prefix for the haplotype identifier", default='haplo_')

parser.add_argument("-acc_prefix", dest="accession_prefix", required=False,
                    help="prefix for FASTA file entries accession", default='enshap_')

parser.add_argument("-log", dest="log_file", required=False,
                    help="output log file", default="prohap.log")

parser.add_argument("-output_csv", dest="output_file", required=True,
                    help="output CSV file")

parser.add_argument("-output_fasta", dest="output_fasta", required=True,
                    help="output FASTA file")

args = parser.parse_args()

print('ProHap: computing protein haplotypes from', args.input_vcf.name)

print ('Reading', args.annotation_db)
# Load the annotations database
annotations_db = gffutils.FeatureDB(args.annotation_db)

print ('Reading', args.transcript_list.name)
# read the list of transcript IDs
transcript_list = [ line[:-1].split('.', 1)[0] for line in args.transcript_list.readlines() ]

print ('Assigning annotations to transcripts.')
# create a list of transcript features from the annotation db
all_transcripts = []
for transcript_id in transcript_list:
    all_transcripts.append(annotations_db[transcript_id])

all_transcripts.sort(key=lambda x: x.start)

print ('Assigning variants to transcripts.')
# parse the VCF file, get a dataframe of variants for each transcript
vcf_dfs = parse_vcf(all_transcripts, args.input_vcf, annotations_db, args.min_af)

print ('Computing co-occurence of alleles.')
# check co-occurence of alleles -> get the haplotypes for all transcripts
gene_haplo_df = get_gene_haplotypes(all_transcripts, vcf_dfs, args.log_file)

# filter the haplotypes by FoO
gene_haplo_df = gene_haplo_df[gene_haplo_df['Frequency'] >= args.min_foo]

# read the CDS sequence file
print ("Reading", args.cdnas_fasta)
all_cds = read_fasta(args.cdnas_fasta)

print ('Creating haplotype database.')
# align the variant coordinates to transcript, translate into the protein database
process_store_haplotypes(gene_haplo_df, all_cds, annotations_db, args.fasta_tag, args.haplo_id_prefix, args.accession_prefix, args.output_file, args.output_fasta)