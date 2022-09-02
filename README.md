# ProHap & ProVar
Proteogenomics database-generation tool for protein haplotypes and variants 

## Input & Usage
Required ingredients:
 - GTF annotation file (Ensembl)
 - cDNA FASTA file (Ensembl)
 - (optional) ncRNA FASTA file (Ensembl)
 - contaminant sequences FASTA (such as https://www.thegpm.org/crap/)
 - ProHap: VCF with phased genotpyes, one file per chromosome \(such as [1000 Genomes Project](http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/)\)
 - ProVar: VCF, one file per chromosome

Required software: snakemake & conda

Usage:
 1. create a configuration file called `config.yaml` based on the instructions in `config_file_example`
 2. run the Snakemake pipeline to create your protein database: `snakemake -c<# provided cores> -p --use-conda`

## Output
### FASTA protein database
The protein sequences are first split into sub-sequences by start and stop codon positions, and then duplicate sequences are aggregated into one FASTA entry. The resulting file has the following format:
```
>tag|accession|<positions_within_protein> <protein_IDs> <protein_starts> <matching_proteins> <reading_frames>
PROTEINSEQUENCE
```
Possible tag values are:
 - `generic_cont`: At least one of the matching sequences belongs to a contaminant.
 - `generic_ref`: No matching contaminant, at least one of the matching sequences belongs to a canonical protein.
 - `generic_var`: No matching contaminant or canonical protein, at least one of the matching sequences belongs to a variant protein.
 - `generic_hap`: No matching contaminant, canonical or variant protein, all of the matching sequences belong to a non-canonical protein haplotype.

The tag values for haplotypes and variants are customizable in the config file. 

The fields included in the description of the FASTA elements are the following:
 - `positions_within_protein`: position of matching sub-sequences within the whole protein sequence, delimited by semicolon
 - `protein_IDs`: IDs of the sub-sequences after splitting the whole protein (redundant)
 - `protein_starts`: positions of the start residue (usually M) within the whole protein, if known (0 otherwise)
 - `matching_proteins`: IDs of the whole protein sequences matching to this sub-sequence. Variant and haplotype IDs can be mapped to the metadata table provided.
 - `reading_frames`: Reading frames in which the matching proteins are translated, if known.

### Metadata table
Metadata file provided in a tab-separated text-file format. The columns are:
 - `chromosome`
 - `TranscriptID`
 - `transcript_biotype`: Biotype of the matching transcript in Ensembl.
 - `HaplotypeID`: ID of the haplotype sequence, matching to the ID in the FASTA entry description.
 - `VCF_IDs`: IDs of the matching lines in the VCF file of provided
 - `DNA_changes`: List of changes in the format POS:REF>ALT, mapped to the DNA coordinates within the chromosome
 - `allele_frequencies`: List of allele vrequencies of the variants in cluded in this haplotype
 - `cDNA_changes`: List of changes in the format POS:REF>ALT, mapped to the coordinates within the cDNA of this transcript
 - `all_protein_changes`: List of changes in the format POS:REF>ALT, mapped to the coordinates within the protein sequence. The start codon is at position 0, so if a change happens in the 5' untranslated region (UTR), its coordinates within the protein are negative.
 - `protein_changes`: List of changes in the protein excluding synonymous mutations.
 - `reading_frame`: Canonical reading frame for this transcript, if known.
 - `protein_prefix_length`: Number of codons in the 5' UTR
 - `splice_sites_affected`: List of splice sites affected by a mutation, if any. (Splice site 0 happens between exon 1 and 2)
 - `occurrence_count`: Number of occurrences of this haplotype within the participants of the 1000 Genomes project (or within the individuals provided in the phased genotype VCF)
 - `frequency`: Frequency of this haplotype within the participants of the 1000 Genomes project (or within the individuals provided in the phased genotype VCF)
