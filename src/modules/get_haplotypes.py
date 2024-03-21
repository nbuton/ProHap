import pandas as pd
import bisect
from multiprocessing import Pool

result_columns = [
    "TranscriptID",
    "Changes",
    "AlleleFrequencies",
    "VCF_IDs",
    "Count",
    "Samples",
]


# group mutations to see which ones conflict
def cluster_conflicting_mutations(changes):
    eventQ = [{"loc": ch["change"][0], "type": "s", "id": ch["id"]} for ch in changes]
    eventQ.extend(
        [
            {"loc": ch["change"][0] + len(ch["change"][1]), "type": "e", "id": ch["id"]}
            for ch in changes
        ]
    )

    eventQ.sort(key=lambda x: x["loc"])

    active_ids = []  # mutations overlapping current position
    id_groups = []  # all the groups of mutations already passed
    current_group = []  # list for aggregating currently overlapping mutations

    for evt in eventQ:
        if evt["type"] == "s":
            active_ids.append(evt["id"])
            current_group.append(evt["id"])

        elif evt["type"] == "e":
            active_ids.remove(evt["id"])

            if len(active_ids) == 0:
                id_groups.append(current_group)
                current_group = []

    return id_groups


# check the list of mutations for any potential conflicts (multiple mutations affecting the same locus)
# if there are multiple mutations conflicting, gradually remove the one with lowest AF until no conflicts
# CURRENTLY NOT USED
def remove_conflicting_mutations(changes, AFs):
    changes_enum = [{"change": ch, "id": i} for i, ch in enumerate(changes)]
    id_groups = cluster_conflicting_mutations(changes_enum)

    result_kept = []
    result_removed = []

    while len(id_groups) > 0:
        tmp_groups = []

        for group in id_groups:
            if len(group) == 1:  # no conflifting mutations here
                result_kept.append(group[0])
            else:
                group_sorted = sorted(group, key=lambda i: float(AFs[i]))
                result_removed.append(
                    group_sorted.pop(0)
                )  # remove the mutation with lowest AF
                group_changes = [changes_enum[i] for i in group_sorted]

                tmp_groups.extend(cluster_conflicting_mutations(group_changes))

        id_groups = tmp_groups

    return result_kept, result_removed


# Creates a list of observed haplotypes from VCF files (individual file for each transcript, with phased genotypes).
# Returns a dataframe, haplotypes described by DNA location, reference and alternative allele.
def get_gene_haplotypes(
    all_transcripts,
    indiv_ids,
    tmp_dir,
    log_file,
    threads,
    is_X_chrom,
    PAR1_to,
    PAR2_from,
    sample_info,
):

    result_data = []
    removed_samples = (
        {}
    )  # Dict giving the list of removed samples by transcript (samples are removed if there are conflicting mutations found)
    indiv_count = 0  # number of individuals in the dataset
    x_autosomal_transcripts = (
        []
    )  # list of transcripts in the pseudo-autosomal region (PAR), only applicable for X chromosome

    # the VCF dataframes all have the same columns -> store the IDs (colnames) of included infividuals:
    indiv_count = len(indiv_ids)

    # keep the sample metadata only for the samples that are in the VCF file - important for frequencies
    sample_info = sample_info[sample_info["Sample name"].isin(indiv_ids)]

    # number of samples in each population
    pop_counts = (
        sample_info[["Population code", "Sample name"]]
        .groupby("Population code")
        .count()
    )
    pop_counts_male = (
        sample_info[sample_info["Sex"] == "male"][["Population code", "Sample name"]]
        .groupby("Population code")
        .count()
    )

    superpop_counts = (
        sample_info[["Superpopulation code", "Sample name"]]
        .groupby("Superpopulation code")
        .count()
    )
    superpop_counts_male = (
        sample_info[sample_info["Sex"] == "male"][
            ["Superpopulation code", "Sample name"]
        ]
        .groupby("Superpopulation code")
        .count()
    )

    sample_info.set_index("Sample name", inplace=True)

    male_samples = [
        sampleID
        for sampleID in indiv_ids
        if (sample_info.loc[sampleID]["Sex"] == "male")
    ]

    global get_haplotypes

    # check haplotypes for every transcript in the DB -> return the ID, payload of the dataframe, and list of samples removed because of conflicting mutations
    def get_haplotypes(transcript):
        transcriptID = transcript.id

        result_local = []

        is_autosomal = (
            (not is_X_chrom)
            or ((transcript.start < PAR1_to) and (transcript.end <= PAR1_to))
            or ((transcript.start >= PAR2_from) and (transcript.end > PAR2_from))
        )

        # load the according VCF file to Pandas
        vcf_df = pd.read_csv(tmp_dir + "/" + transcriptID + ".tsv", sep="\t")

        # no variation in this transcript -> store reference haplotype only
        if len(vcf_df) == 0:
            return [
                {
                    "id": transcriptID,
                    "data": [transcriptID, "REF", "", "", indiv_count * 2, "all"],
                    "removed_samples": [],
                    "autosomal": is_autosomal,
                }
            ]

        haplo_combinations = []
        haplo_samples = []
        removed_haplo_samples = []

        # check the combination for every individual
        for indiv in indiv_ids:

            # store indices of rows for which the alternative allele has been found -> create a temporary string ID of the haplotype
            vals = vcf_df[indiv].to_list()
            vals = [v.replace("/", "|").split(":")[0] for v in vals]

            # sanity check - correct separator between paternal / maternal chromosome
            err_rows = ",".join(
                [str(i) for i, elem in enumerate(vals) if "|" not in elem]
            )

            if len(err_rows) > 1:
                print(
                    "Incorrect formatting!",
                    "individual:",
                    indiv,
                    "rows:",
                    err_rows,
                    "transcript:",
                    transcriptID,
                )

            hap1 = ",".join(
                [str(i) for i, elem in enumerate(vals) if elem.startswith("1|")]
            )
            hap2 = None
            if is_autosomal or (
                indiv not in male_samples
            ):  # males have alleles for the X chromosome specified on the first copy, second copy is always 0
                hap2 = ",".join(
                    [str(i) for i, elem in enumerate(vals) if elem.endswith("|1")]
                )

            # no alternative alleles -> reference haplotype
            if hap1 == "":
                hap1 = "REF"
            if hap2 == "":
                hap2 = "REF"

            # find if this haplotype has been identified before
            # if so, add this individual to the list, otherwise add new haoplotype
            nearest_idx = bisect.bisect_left(haplo_combinations, hap1)
            if (
                len(haplo_combinations) > nearest_idx
                and haplo_combinations[nearest_idx] == hap1
            ):
                haplo_samples[nearest_idx].append(indiv + ":1")
            else:
                haplo_combinations.insert(nearest_idx, hap1)
                haplo_samples.insert(nearest_idx, [indiv + ":1"])

            if hap2 is not None:
                nearest_idx = bisect.bisect_left(haplo_combinations, hap2)
                if (
                    len(haplo_combinations) > nearest_idx
                    and haplo_combinations[nearest_idx] == hap2
                ):
                    haplo_samples[nearest_idx].append(indiv + ":2")
                else:
                    haplo_combinations.insert(nearest_idx, hap2)
                    haplo_samples.insert(nearest_idx, [indiv + ":2"])

        # once all individuals in this VCF have been processed -> summarize observed haplotypes, compute worldwide frequencies
        for i, combination in enumerate(haplo_combinations):
            if combination == "REF":
                changes_str = "REF"
                AFs_str = ""
                combination = ""
                # removed_str = ""
                vcf_IDs = []

            else:
                indexes = [int(idx) for idx in combination.split(",")]
                changes = []  # changes in the POS:REF>ALT formatk
                changelist = []  # changes with the POS, REF and ALT fields sepatared
                AFs = []  # allele frequencies
                vcf_IDs = []  # IDs in the VCF file

                for idx in indexes:
                    row = vcf_df.iloc[idx]

                    vcf_IDs.append(str(row["ID"]))

                    changelist.append([row["POS"], row["REF"], row["ALT"]])
                    changes.append(
                        str(row["POS"]) + ":" + row["REF"] + ">" + row["ALT"]
                    )
                    if "AF" in row["INFO"]:
                        AFs.append(
                            row["INFO"]
                            .split("AF=")[1]
                            .split(";")[0]
                            .split(maxsplit=1)[0]
                        )
                    else:
                        AFs.append("-1")

                # check for conflicting mutations! -> remove these samples from analysis if conflicts found
                changes_enum = [
                    {"change": ch, "id": i} for i, ch in enumerate(changelist)
                ]
                changes_clustered = cluster_conflicting_mutations(changes_enum)
                conflict_found = False
                for cluster in changes_clustered:
                    if len(cluster) > 1:
                        removed_haplo_samples.extend(haplo_samples[i])

                        conflict_found = True
                        break

                if conflict_found:
                    continue

                # kept, removed = remove_conflicting_mutations(changelist, AFs)
                # removedChanges = [ changes[i] for i in removed ]
                # changelist = [ changelist[i] for i in kept ]
                # changes = [ changes[i] for i in kept ]
                # AFs = [ AFs[i] for i in kept ]

                # sort the changes according to the position
                zipped = list(zip(changelist, changes, AFs))
                zipped.sort(key=lambda x: int(x[0][0]))
                changelist, changes, AFs = zip(*zipped)

                # removed_str = ';'.join(removedChanges)
                changes_str = ";".join(changes)
                AFs_str = ";".join(AFs)

            result_local.append(
                {
                    "id": transcriptID,
                    "data": [
                        transcriptID,
                        changes_str,
                        AFs_str,
                        ";".join(vcf_IDs),
                        len(haplo_samples[i]),
                        ";".join(haplo_samples[i]),
                    ],
                    "removed_samples": removed_haplo_samples,
                    "autosomal": is_autosomal,
                }
            )

        return result_local

    with Pool(threads) as p:
        aggregated_results = p.map(get_haplotypes, all_transcripts)
    # aggregated_results = list(map(get_haplotypes, all_transcripts))

    for processed_transcript in aggregated_results:
        for elem in processed_transcript:
            result_data.append(elem["data"])

            removed_samples[elem["id"]] = elem["removed_samples"]

            if is_X_chrom and elem["autosomal"]:
                x_autosomal_transcripts.append(elem["id"])

    result_df = pd.DataFrame(columns=result_columns, data=result_data)
    print("result_df:")
    print(result_df)

    # count frequencies taking into account the number of removed samples in the transcript, and sex in case of X chromosome
    def count_freq(row):
        id = row["TranscriptID"]
        # removed_count = len(removed_samples[id])
        total_count = 0

        if is_X_chrom and (id not in x_autosomal_transcripts):
            male_count = len(male_samples)
            total_count = male_count + (
                (indiv_count - male_count) * 2
            )  # - removed_count
        else:
            total_count = indiv_count * 2  # - removed_count

        if total_count == 0:
            return 0

        return row["Count"] / total_count

    # count the occurrences of this haplotype within populations and superpopulations
    def count_freq_pop(row):
        populations = {}

        if row["Samples"] == "all":
            return "-"

        for s in row["Samples"].split(";"):
            pop_code = sample_info.loc[s.split(":", 1)[0]]["Population code"]

            if pop_code in populations:
                populations[pop_code] += 1
            else:
                populations[pop_code] = 1

        id = row["TranscriptID"]
        result = []

        for pop_code in populations:
            pop_indiv_count = pop_counts.loc[pop_code]["Sample name"]
            pop_total_count = 0
            pop_freq = 0

            if is_X_chrom and (id not in x_autosomal_transcripts):
                pop_male_count = pop_counts_male.loc[pop_code]["Sample name"]
                pop_total_count = pop_male_count + (
                    (pop_indiv_count - pop_male_count) * 2
                )
            else:
                pop_total_count = pop_indiv_count * 2

            if pop_total_count > 0:
                pop_freq = populations[pop_code] / pop_total_count
                result.append(pop_code + ":{:.5f}".format(pop_freq))

        return ";".join(result)

    def count_freq_superpop(row):
        superpop = {}

        if row["Samples"] == "all":
            return "-"

        for s in row["Samples"].split(";"):
            superpop_code = sample_info.loc[s.split(":", 1)[0]]["Superpopulation code"]

            if superpop_code in superpop:
                superpop[superpop_code] += 1
            else:
                superpop[superpop_code] = 1

        id = row["TranscriptID"]
        result = []

        for pop_code in superpop:
            pop_indiv_count = superpop_counts.loc[pop_code]["Sample name"]
            pop_total_count = 0
            pop_freq = 0

            if is_X_chrom and (id not in x_autosomal_transcripts):
                pop_male_count = superpop_counts_male.loc[pop_code]["Sample name"]
                pop_total_count = pop_male_count + (
                    (pop_indiv_count - pop_male_count) * 2
                )
            else:
                pop_total_count = pop_indiv_count * 2

            if pop_total_count > 0:
                pop_freq = superpop[pop_code] / pop_total_count
                result.append(pop_code + ":{:.5f}".format(pop_freq))

        return ";".join(result)

    result_df["Frequency"] = result_df.apply(count_freq, axis=1)
    result_df["Frequency_population"] = result_df.apply(count_freq_pop, axis=1)
    result_df["Frequency_superpopulation"] = result_df.apply(
        count_freq_superpop, axis=1
    )
    # result_df.sort_values(by=['TranscriptID', 'Frequency'], ascending=[True, False], inplace=True)

    # write info about the removed samples into the log file
    log_file_handle = open(log_file, "w")
    log_file_handle.write("TranscriptID\t#Removed\tRemovedSamples\n")

    for transcript in removed_samples:
        log_file_handle.write(
            transcript
            + "\t"
            + str(len(removed_samples[transcript]))
            + "\t"
            + ";".join(removed_samples[transcript])
            + "\n"
        )
    log_file_handle.close()

    return result_df
