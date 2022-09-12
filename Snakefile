configfile: "config.yaml"

VARIANT_VCF_FILES = config['variant_vcf']
CHROMOSOMES = [str(x) for x in list(range(1, 23))] + ['X']

WORKING_DIR_NAME_HAPLO = config['working_dir_name_haplo']
WORKING_DIR_NAME_VAR = config['working_dir_name_var']

rule all:
    input:
        final_fasta=config['final_fasta_file'],
        var_table=config['var_table_file'],
        haplo_table=config['haplo_table_file']


rule download_vcf:
    output:
        "data/1000genomes_GRCh38_30x_vcf/" + config['1kGP_vcf_file_name_30']
    shell:
        "wget " + config['1000Gs30_URL'] + config['1kGP_vcf_file_name_30'].replace('{chr}', '{wildcards.chr}') + ".gz -O {output}.gz  && gunzip {output}.gz"

rule download_gtf:
    output:
        "data/gtf/" + config['annotationFilename'] + ".gtf"
    shell:
        "wget " + config['EnsemblFTP'] + "gtf/homo_sapiens/" + config['annotationFilename'] + ".gtf.gz -O {output}.gz && gunzip {output}.gz; "

rule download_cdnas_fasta:
    output:
        out1="data/fasta/Homo_sapiens.GRCh38.ncrna.fa",
        out2="data/fasta/Homo_sapiens.GRCh38.cdna.all.fa"
    shell:
        "wget " + config['EnsemblFTP'] + "fasta/homo_sapiens/ncrna/Homo_sapiens.GRCh38.ncrna.fa.gz -O {output.out1}.gz && gunzip {output.out1}.gz; "
        "wget " + config['EnsemblFTP'] + "fasta/homo_sapiens/cdna/Homo_sapiens.GRCh38.cdna.all.fa.gz -O {output.out2}.gz && gunzip {output.out2}.gz; "

rule merge_cdnas_fasta:
	input:
		in1="data/fasta/Homo_sapiens.GRCh38.ncrna.fa",
		in2="data/fasta/Homo_sapiens.GRCh38.cdna.all.fa"
	output:
		"data/fasta/total_cdnas.fa"
	shell:
		"cat {input.in1} > {output}; cat {input.in2} >> {output}"

rule download_reference_proteome:
    output:
        "data/fasta/Homo_sapiens.GRCh38.pep.all.fa"
    shell:
        "wget " + config['EnsemblFTP'] + "fasta/homo_sapiens/pep/Homo_sapiens.GRCh38.pep.all.fa.gz -O {output}.gz && gunzip {output}.gz; "

rule reference_fix_headers:
	input:
		"data/fasta/Homo_sapiens.GRCh38.pep.all.fa"
	output:
		"data/fasta/ensembl_reference_proteinDB_tagged.fa"
	shell:
		"python3 src/fix_headers.py -i {input} -o {output} -t _ensref "

rule reference_remove_stop:
    input:
        "data/fasta/ensembl_reference_proteinDB_tagged.fa"
    output:
        "data/fasta/ensembl_reference_proteinDB_clean.fa"
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 8 "

rule contaminants_fix_headers:
	input:
		"crap.fasta"
	output:
		"data/fasta/crap_tagged.fa"
	shell:
		"python3 src/fix_headers.py -i {input} -o {output} -t _cont"

# filter the GTF so that only features on one chromosome are present:
rule split_gtf:
    input:
        "data/gtf/" + config['annotationFilename'] + ".gtf"
    output:
        "data/gtf/" + config['annotationFilename'] + "_chr{chr}.gtf"
    shell:
        "grep \"^#\" {input} > {output}; "
        "grep \"^{wildcards.chr}\s\" {input} >> {output}"

# create the DB files from GTF for each chromosome
rule parse_gtf:
    input:
        "data/gtf/" + config['annotationFilename'] + "_chr{chr}.gtf"
    output:
        db="data/gtf/" + config['annotationFilename'] + "_chr{chr}.db",
        tr="data/chr{chr}_transcripts.txt"
    shell:
        "python3 src/parse_gtf.py -i {input} -o {output.db} -noncoding 0 -transcript_list {output.tr}"

rule compute_variants:
    input:
        db="data/gtf/" + config['annotationFilename'] + "_chr{chr}.db",
        tr="data/chr{chr}_transcripts.txt",
        vcf=lambda wildcards: VARIANT_VCF_FILES[f"{wildcards.vcf}"]['file_prefix'] + f"_chr{wildcards.chr}.vcf",
        fasta="data/fasta/total_cdnas.fa",
    output:
        tsv="results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_chr{chr}.tsv",
        fasta="results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_chr{chr}.fa"
    params:
        acc_prefix=lambda wildcards: VARIANT_VCF_FILES[f"{wildcards.vcf}"]['fasta_accession_prefix'],
        log_file="log/{vcf}_chr{chr}.log"
    shell:
        "python3 src/provar.py "
         "-i {input.vcf} -db {input.db} -transcripts {input.tr} -cdna {input.fasta} "
         "-chr {wildcards.chr} -acc_prefix {params.acc_prefix} -af 0.01 "
         "-log {params.log_file} -tmp_dir tmp/transcript_vcf -output_csv {output.tsv} -output_fasta {output.fasta} ;"

rule merge_var_tables_vcf:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.tsv", chr=CHROMOSOMES)
    output:
        temp("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.tsv")
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.tsv", chr=CHROMOSOMES))
    shell:
        "python3 src/merge_tables.py -i {params.input_file_list} -o {output}"

rule merge_var_fasta_vcf:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.fa", chr=CHROMOSOMES)
    output:
        temp("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.fa")
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.fa", chr=CHROMOSOMES))
    shell:
        "cat {input} > {output}"

rule merge_var_tables:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.tsv", vcf=VARIANT_VCF_FILES.keys())
    output:
        config['var_table_file']
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.tsv", vcf=VARIANT_VCF_FILES.keys()))
    shell:
        "python3 src/merge_tables.py -i {params.input_file_list} -o {output}"

rule merge_var_fasta:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.fa", vcf=VARIANT_VCF_FILES.keys())
    output:
        temp("results/" + WORKING_DIR_NAME_VAR + "/variants_all.fa")
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.fa", vcf=VARIANT_VCF_FILES.keys()))
    shell:
        "cat {input} > {output}"

rule var_fasta_remove_stop:
    input:
        "results/" + WORKING_DIR_NAME_VAR + "/variants_all.fa"
    output:
        temp("results/" + WORKING_DIR_NAME_VAR + "/variants_all_clean.fa")
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 8 "

rule compute_haplotypes:
    input:
        db="data/gtf/" + config['annotationFilename'] + "_chr{chr}.db",
        tr="data/chr{chr}_transcripts.txt",
        vcf="data/1000genomes_GRCh38_30x_vcf/" + config['1kGP_vcf_file_name_30'],
        fasta="data/fasta/total_cdnas.fa",
        samples="igsr_samples.tsv"
    output:
        csv="results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv",
        fasta="results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa"
    params:
        log_file="log/chr{chr}.log"
    threads: 3
    shell:
        "python3 src/prohap.py "
        "-i {input.vcf} -db {input.db} -transcripts {input.tr} -cdna {input.fasta} -s {input.samples} "
        "-chr {wildcards.chr} -af 0.01 -foo 0.01 -acc_prefix enshap_{wildcards.chr} -id_prefix haplo_chr{wildcards.chr} "
        "-threads 3 -log {params.log_file} -tmp_dir tmp/transcript_vcf -output_csv {output.csv} -output_fasta {output.fasta} "

rule merge_haplo_tables:
    input:
        expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv", chr=CHROMOSOMES)
    output:
        config['haplo_table_file']
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv", chr=CHROMOSOMES))
    shell:
        "python3 src/merge_tables.py -i {params.input_file_list} -o {output}"

rule merge_fasta:
    input:
        expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa", chr=CHROMOSOMES)
    output:
        temp("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_all.fa")
    params:
        input_file_list = ' '.join(expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa", chr=CHROMOSOMES))
    shell:
        "cat {input} > {output}"

rule haplo_fasta_remove_stop:
    input:
        "results/" + WORKING_DIR_NAME_HAPLO + "/haplo_all.fa"
    output:
        temp("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_all_clean.fa")
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 8 "

rule mix_with_reference_proteome:
	input:
		in1="data/fasta/ensembl_reference_proteinDB_clean.fa",
                in2="data/fasta/crap_tagged.fa",
		in3=expand('{proxy}', proxy=["results/" + WORKING_DIR_NAME_VAR + "/variants_all_clean.fa"] if config["include_var"] else []),
		in4=expand('{proxy}', proxy=["results/" + WORKING_DIR_NAME_HAPLO + "/haplo_all_clean.fa"] if config["include_haplo"] else []),
	output:
		temp("results/" + WORKING_DIR_NAME_VAR + "/ref_contam_vcf_haplo_all_clean.fa")		
	run:
		shell("cat {input.in1} {input.in2} > {output}; ")
		if config["include_var"]:
			shell("cat {input.in3} >> {output}")
		if config["include_haplo"]:
			shell("cat {input.in4} >> {output}")

rule merge_duplicate_seq:
	input:
		"results/" + WORKING_DIR_NAME_VAR + "/ref_contam_vcf_haplo_all_clean.fa"
	output:
		temp("results/" + WORKING_DIR_NAME_VAR + "/ref_contam_vcf_haplo_all_nodupl.fa")
		#config['final_fasta_file']
	shell:
		"python3 src/merge_duplicate_seq.py -i {input} -o {output} "

rule remove_UTR_seq:
	input:
		"results/" + WORKING_DIR_NAME_VAR + "/ref_contam_vcf_haplo_all_nodupl.fa"
	output:
		config['final_fasta_file']
	shell:
		"python src/remove_UTR_seq.py -i {input} -o {output}"


