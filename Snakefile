configfile: "config.yaml"

VARIANT_VCF_FILES = config['variant_vcf']
CHROMOSOMES = [str(x) for x in list(range(1, 23))] + ['X']

WORKING_DIR_NAME_HAPLO = config['working_dir_name_haplo']
WORKING_DIR_NAME_VAR = config['working_dir_name_var']

rule all:
    input:
        final_fasta=config['final_fasta_file'],
        var_table=expand('{proxy}', proxy=[config['var_table_file']] if config["use_ProVar"] else []),
        haplo_table=expand('{proxy}', proxy=[config['haplo_table_file']] if config["use_ProHap"] else []),
        var_fasta=expand('{proxy}', proxy=[config['var_fasta_file']] if config["use_ProVar"] else []),
        haplo_fasta=expand('{proxy}', proxy=[config['haplo_fasta_file']] if config["use_ProHap"] else []),

rule download_vcf:
    output:
        temp("data/vcf/phased/" + config['phased_vcf_file_name'])
    shell:
        "mkdir -p data/vcf/phased ; "
        "wget " + config['phased_FTP_URL'] + config['phased_vcf_file_name'].replace('{chr}', '{wildcards.chr}') + ".gz -O {output}.gz  && gunzip {output}.gz"

rule download_gtf:
    output:
        temp("data/gtf/" + config['annotationFilename'] + ".gtf")
    shell:
        "mkdir -p data/gtf ; "
        "wget " + config['Ensembl_FTP_URL'] + "gtf/homo_sapiens/" + config['annotationFilename'] + ".gtf.gz -O {output}.gz && gunzip {output}.gz; "

rule parse_gtf_whole:
    input:
        "data/gtf/" + config['annotationFilename'] + ".gtf"
    output:
        temp("data/gtf/" + config['annotationFilename'] + ".db")
    shell:
        "python3 src/parse_gtf.py -i {input} -o {output}"

rule get_transcript_list:
    input:
        "data/gtf/" + config['annotationFilename'] + ".db"
    output:
        temp("data/included_transcripts.csv")
    params:
        biotypes=config['included_transcript_biotypes']
    shell:
        "python3 src/get_transcript_list.py -i {input} -bio {params.biotypes} -o {output}"

rule download_cdnas_fasta:
    output:
        out1=temp("data/fasta/Homo_sapiens.GRCh38.ncrna.fa"),
        out2=temp("data/fasta/Homo_sapiens.GRCh38.cdna.all.fa")
    shell:
        "mkdir -p data/fasta ; "
        "wget " + config['Ensembl_FTP_URL'] + "fasta/homo_sapiens/ncrna/Homo_sapiens.GRCh38.ncrna.fa.gz -O {output.out1}.gz && gunzip {output.out1}.gz; "
        "wget " + config['Ensembl_FTP_URL'] + "fasta/homo_sapiens/cdna/Homo_sapiens.GRCh38.cdna.all.fa.gz -O {output.out2}.gz && gunzip {output.out2}.gz; "

rule merge_cdnas_fasta:
	input:
		in1="data/fasta/Homo_sapiens.GRCh38.ncrna.fa",
		in2="data/fasta/Homo_sapiens.GRCh38.cdna.all.fa"
	output:
		"data/fasta/total_cdnas_" + str(config['ensembl_release']) + ".fa"
	shell:
		"cat {input.in1} > {output}; cat {input.in2} >> {output}"

rule download_reference_proteome:
    output:
        temp("data/fasta/Homo_sapiens.GRCh38.pep.all.fa")
    shell:
        "mkdir -p data/fasta ; "
        "wget " + config['Ensembl_FTP_URL'] + "fasta/homo_sapiens/pep/Homo_sapiens.GRCh38.pep.all.fa.gz -O {output}.gz && gunzip {output}.gz; "

rule reference_fix_headers:
    input:
        "data/fasta/Homo_sapiens.GRCh38.pep.all.fa"
    output:
        "data/fasta/ensembl_reference_proteinDB_" + str(config['ensembl_release']) + "_tagged.fa"
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/fix_headers.py -i {input} -o {output} -t _ensref -use_ENST 1 "

rule default_transcript_list:
    input:
        "data/fasta/ensembl_reference_proteinDB_" + str(config['ensembl_release']) + "_tagged.fa"
    output:
        "data/transcripts_reference_" + str(config['ensembl_release']) + ".csv"
    shell:
        "python3 src/get_reference_ENST.py -i {input} -o {output}"

rule reference_remove_stop:
    input:
        "data/fasta/ensembl_reference_proteinDB_" + str(config['ensembl_release']) + "_tagged.fa"
    output:
        temp("data/fasta/ensembl_reference_proteinDB_" + str(config['ensembl_release']) + "_clean.fa")
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 6 "

rule contaminants_fix_headers:
    input:
        "crap.fasta"
    output:
        "data/fasta/crap_tagged.fa"
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/fix_headers.py -i {input} -o {output} -t _cont"

# filter the GTF so that only features on the desired chromosome are present
rule split_gtf:
    input:
        "data/gtf/" + config['annotationFilename'] + ".gtf"
    output:
        temp("data/gtf/" + config['annotationFilename'] + "_chr{chr}.gtf")
    shell:
        "grep \"^#\" {input} > {output}; "
        "grep \"^{wildcards.chr}\s\" {input} >> {output}"

# create the DB files from GTF for each chromosome
rule parse_gtf_chromosome:
    input:
        "data/gtf/" + config['annotationFilename'] + "_chr{chr}.gtf"
    output:
        temp("data/gtf/" + config['annotationFilename'] + "_chr{chr}.db")
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/parse_gtf.py -i {input} -o {output}"

# ------------------------------------ ProVar rules ------------------------------------

rule split_variant_vcf:
    input:
        lambda wildcards: VARIANT_VCF_FILES[f"{wildcards.vcf}"]['file']
    output:
        temp("tmp/variants_{vcf}/ready")
    params:
        output_prefix="tmp/variants_{vcf}/variants"
    conda: "envs/prohap.yaml"
    shell:
        "python src/fragment_variant_vcf.py -i {input} -o {params.output_prefix} ; touch {output}"

rule compute_variants:
    input:
        db="data/gtf/" + config['annotationFilename'] + "_chr{chr}.db",
        tr=expand('{proxy}', proxy=[config['custom_transcript_list']] if len(config["custom_transcript_list"]) > 0 else ["data/included_transcripts.csv"]),
        fasta="data/fasta/total_cdnas_" + str(config['ensembl_release']) + ".fa",
        flag="tmp/variants_{vcf}/ready",
    output:
        tsv=temp("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_chr{chr}.tsv"),
        fasta=temp("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_chr{chr}.fa")
    params:
        input_vcf="tmp/variants_{vcf}/variants_chr{chr}.vcf",
        acc_prefix=lambda wildcards: VARIANT_VCF_FILES[f"{wildcards.vcf}"]['fasta_accession_prefix'],
        min_af=lambda wildcards: VARIANT_VCF_FILES[f"{wildcards.vcf}"]['min_af'],
        log_file="log/{vcf}_chr{chr}.log",
        #log_file="log/provar.log",
        tmp_dir="tmp/transcripts_{vcf}",
        require_start=config['var_require_start']
    conda: "envs/prohap.yaml"
    shell:
        "mkdir -p {params.tmp_dir}; mkdir -p log; mkdir -p results; "
        "python3 src/provar.py "
        "-i {params.input_vcf} -db {input.db} -transcripts {input.tr} -cdna {input.fasta} "
        "-chr {wildcards.chr} -acc_prefix {params.acc_prefix}_chr{wildcards.chr} -af {params.min_af} -require_start {params.require_start} "
        "-log {params.log_file} -tmp_dir {params.tmp_dir} -output_csv {output.tsv} -output_fasta {output.fasta} ;"

rule merge_var_tables_vcf:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.tsv", chr=CHROMOSOMES)
    output:
        temp("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.tsv")
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{{vcf}}/variants_chr{chr}.tsv", chr=CHROMOSOMES))
    conda: "envs/prohap.yaml"
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
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/merge_tables.py -i {params.input_file_list} -o {output}"

rule merge_var_fasta:
    input:
        expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.fa", vcf=VARIANT_VCF_FILES.keys())
    output:
        config['var_fasta_file']
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_VAR + "/variants_{vcf}/variants_all.fa", vcf=VARIANT_VCF_FILES.keys()))
    shell:
        "cat {input} > {output}"

rule var_fasta_remove_stop:
    input:
        config['var_fasta_file']
    output:
        temp("results/variants_all_clean.fa")
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 6 "

# ------------------------------------ ProHap rules ------------------------------------

rule compute_haplotypes:
    input:
        db="data/gtf/" + config['annotationFilename'] + "_chr{chr}.db",
        tr=expand('{proxy}', proxy=[config['custom_transcript_list']] if len(config["custom_transcript_list"]) > 0 else ["data/included_transcripts.csv"]),
        vcf=expand('{proxy}', proxy=[config['phased_local_path'] + config['phased_vcf_file_name']] if len(config["phased_local_path"]) > 0 else ["data/vcf/phased/" + config['phased_vcf_file_name']]),
        fasta="data/fasta/total_cdnas_" + str(config['ensembl_release']) + ".fa",
        samples=config['sample_metadata_file']
    output:
        csv=temp("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv"),
        fasta=temp("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa"),
    params:
        log_file="log/prohap_chr{chr}.log",
        tmp_dir="tmp/transcript_vcf_haplo",
        require_start=config['haplo_require_start'],
        ignore_UTR=config['haplo_ignore_UTR'],
        skip_start_lost=config['haplo_skip_start_lost'],
        freq_threshold=config['haplo_min_freq'],
        count_threshold=config['haplo_min_count'],
        max_cores=config['max_cores']
    threads: config['max_cores']
    conda: "envs/prohap.yaml"
    shell:
        "mkdir -p {params.tmp_dir}; mkdir -p log; mkdir -p results; "
        "python3 src/prohap.py "
        "-i {input.vcf} -db {input.db} -transcripts {input.tr} -cdna {input.fasta} -s {input.samples} "
        "-chr {wildcards.chr} -min_hap_foo {params.freq_threshold} -min_hap_count {params.count_threshold} "
        "-acc_prefix enshap_{wildcards.chr} -id_prefix haplo_chr{wildcards.chr} -require_start {params.require_start} -ignore_UTR {params.ignore_UTR} -skip_start_lost {params.skip_start_lost} "
        "-threads {params.max_cores} -log {params.log_file} -tmp_dir {params.tmp_dir} -output_csv {output.csv} -output_fasta {output.fasta} "

rule merge_haplo_tables:
    input:
        expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv", chr=CHROMOSOMES)
    output:
        config['haplo_table_file']
    params:
        input_file_list = ','.join(expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.tsv", chr=CHROMOSOMES))
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/merge_tables.py -i {params.input_file_list} -o {output}"

rule merge_fasta:
    input:
        expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa", chr=CHROMOSOMES)
    output:
        config['haplo_fasta_file']
    params:
        input_file_list = ' '.join(expand("results/" + WORKING_DIR_NAME_HAPLO + "/haplo_chr{chr}.fa", chr=CHROMOSOMES))
    shell:
        "cat {input} > {output}"

rule haplo_fasta_remove_stop:
    input:
        config['haplo_fasta_file']
    output:
        temp("results/haplo_all_clean.fa")
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 6 "

# ------------------------------------ post-processing rules ------------------------------------

rule added_fasta_remove_stop:
    input:
        config['haplo_added_fasta']
    output:
        temp("results/haplo_added_clean.fa")
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/remove_stop_codons.py -i {input} -o {output} -min_len 6 "

rule mix_with_reference_proteome:
    input:
        in1="data/fasta/ensembl_reference_proteinDB_" + str(config['ensembl_release']) + "_clean.fa",
        in2="data/fasta/crap_tagged.fa",
        in3=expand('{proxy}', proxy=["results/variants_all_clean.fa"] if config["use_ProVar"] else []),
        in4=expand('{proxy}', proxy=["results/haplo_all_clean.fa"] if config["use_ProHap"] else []),
        in5=expand('{proxy}', proxy=["results/haplo_added_clean.fa"] if config["add_existing_haplo"] else []),
    output:
        temp("results/ref_contam_vcf_haplo_all_clean.fa")		
    run:
        shell("cat {input.in1} {input.in2} > {output}; ")
        if config["use_ProVar"]:
            shell("cat {input.in3} >> {output}")
        if config["use_ProHap"]:
            shell("cat {input.in4} >> {output}")
        if config["add_existing_haplo"]:
            shell("cat {input.in5} >> {output}")

rule merge_duplicate_seq:
    input:
        "results/ref_contam_vcf_haplo_all_clean.fa"
    output:
        temp("results/ref_contam_vcf_haplo_all_nodupl.fa")
        #config['final_fasta_file']                         
    conda: "envs/prohap.yaml"
    shell:
        "python3 src/merge_duplicate_seq.py -i {input} -o {output} "

# UTRs in ProHap are removed by default (can be changed), but not in ProVar -> make sure all UTRs are removed
rule remove_UTR_seq:
    input:
        "results/ref_contam_vcf_haplo_all_nodupl.fa"
    output:
        config['final_fasta_file']
    conda: "envs/prohap.yaml"
    shell:
        "python src/remove_UTR_seq.py -i {input} -o {output}"

