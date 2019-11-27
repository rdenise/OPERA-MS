import gzip
import sys
import os
import argparse
import subprocess
import config_parser
import re

util_dir = "/home/bertrandd/PROJECT_LINK/OPERA_LG/META_GENOMIC_HYBRID_ASSEMBLY/OPERA-MS-DEV/OPERA-MS/utils"
"""
qsub -terse -m a -M \$USER_PRINCIPAL_NAME -cwd -V -l mem_free=10G,h_rt=12:0:0 -pe OpenMP 16 -N CFSAN28_MAXBIN -b y perl /mnt/projects/bertrandd/opera_lg/SOFTWARE/MAXBIN/MaxBin-2.2.4/run_MaxBin.pl -min_contig_length 500 -contig ANALYSIS/ASSEMBLY/28h/contig.fasta -reads Illumina_reads/R1_28h_mergedrep.fastq.gz -out ANALYSIS/ASSEMBLY/24h/MAXBIN2/28h_bin -thread 16

/mnt/software/unstowable/miniconda3-4.6.14/envs/metabat2-v2.12.1/bin/metabat -i ANALYSIS/ASSEMBLY/40h/contig.fasta -o test_meta/40h/metabin
"""

# default to look for polish contig, if polished contig not exist, use unpolish.
# if user want to always use unpolish contig, specifiy flag --unploshed

def create_dir(new_dir):
    try:
        os.mkdir(new_dir)
    except:
        pass

    
def run_exe(cmd):
    run = 1
    print(cmd)
    if run:
        return subprocess.check_output(cmd, shell=True)

def get_binner_file_type(binner):
    file_type = "fasta"
    if binner == "metabat2":
        file_type = "fa"
    return file_type
    
def run_binner(binner, sample_name, assembly_dir, short_read1, short_read2, nb_thread):
    
    contig_file = "{}/contigs.fasta".format(assembly_dir)
    
    if os.path.exists('{}/contigs.polished.fasta'.format(assembly_dir)):
        contig_file = "{}/contigs.polished.fasta".format(assembly_dir)

    if binner == "maxbin2":
        run_maxbin2(contig_file, short_read1, assembly_dir, sample_name, nb_thread)
        
    if binner == "metabat2":
        run_metabat2(contig_file, short_read1, short_read2, assembly_dir, sample_name, nb_thread)
        
def run_maxbin2(contig_file, short_read1, assembly_dir, sample_name, nb_thread):
    out_dir = assembly_dir + "/maxbin2"
    create_dir(out_dir)
    out_dir = assembly_dir + "/maxbin2/all"
    create_dir(out_dir)
    run_exe("perl {}/MaxBin-2.2.4/run_MaxBin.pl -min_contig_length 500 -contig {} -reads {} -out {}/{}_bin -thread {}".format(util_dir, contig_file, short_read1, out_dir, sample_name, nb_thread))

def run_metabat2(contig_file, short_read1, short_read2, assembly_dir, sample_name, nb_thread):

    out_dir = assembly_dir + "/metabat2"
    
    #Check if a mapping exists to the unpolished data
    bam_file = assembly_dir + "/intermediate_files/polished_assembly/contigs.fa.bam"

    #Run the mapping
    if not os.path.isfile(bam_file):
        # bwa ref index
        run_exe("{}/bwa index {} > {}/bwa_index.out 2> {}/bwa_index.err".format(util_dir, contig_file, assembly_dir, assembly_dir))

        # bwa mapping
        run_exe("{}/bwa mem -t {} {} {} {} | {}/samtools view -Sub - | {}/samtools sort - {} > {}/bwa.out 2>> {}/bwa.err".format(util_dir, nb_thread, contig_file, short_read1, short_read2, util_dir, util_dir, contig_file, assembly_dir, assembly_dir))

        # bwa bam index
        bam_file = contig_file + ".bam"
        run_exe("{}/samtools index {} >> {}/bwa.out 2>> {}/bwa.err".format(util_dir, bam_file, assembly_dir, assembly_dir))


    #Create the output directory
    create_dir(out_dir)
    out_dir = assembly_dir + "/metabat2/all"
    create_dir(out_dir)
    
    # metabat depth file
    run_exe("{}/jgi_summarize_bam_contig_depths --outputDepth {}/output_depth {}".format(util_dir, out_dir, bam_file))
    
    # run metabat
    run_exe("{}/metabat --unbinned -i {} -a {}/output_depth -o {}/{}_bin -t {}".format(util_dir, contig_file, out_dir, out_dir, sample_name, nb_thread))


def run_checkm(bin_dir, checkm_dir, suffix, nb_thread, eval_file):
    #Run the checkm analysis
    if not os.path.exists(eval_file):
        run_exe("{}/checkm lineage_wf -t {}  -x {} {}/ {}".format(util_dir, nb_thread, suffix, bin_dir, checkm_dir))
        run_exe("{}/checkm qa -o 2 {}/lineage.ms {} > {}".format(util_dir, checkm_dir, checkm_dir, eval_file))
    else:
        print("CheckM result detected skip analysis")

def identify_high_medium_bin(binner_dir, eval_file, high_qual_mags, medium_qual_mags):
    high_qual_threshold = [float(item) for item in high_qual_mags.split(',')]
    medium_qual_threshold = [float(item) for item in medium_qual_mags.split(',')]
    #
    high_dir = binner_dir + "/high_quality"
    medium_dir = binner_dir + "/medium_quality"

    try:
        run_exe("rm -r " + high_dir + " " + medium_dir)
    except:
        pass
    
    create_dir(high_dir)
    create_dir(medium_dir)
    #
    print(high_qual_threshold)
    FILE = open(eval_file, "r")
    OUT = open(binner_dir + "/bin_info.txt", "w")
    bin_id = bin_status = bin_out_dir = ""
    bin_size, bin_nb_contig, bin_longest_contig, bin_n50, bin_contamination, bin_completness = 0, 0, 0, 0, 0, 0
    OUT.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format("ID", "Status", "Completness", "Contamination",  "Size", "#_contigs", "Contig_N50", "Longuest_contig"))
    for line in FILE:
        #print line
        line_list = re.split(" \s+", line)
        if len(line_list) != 1 and line_list[1] != "Bin Id":
            bin_id = line_list[1]
            bin_status = "LOW"
            bin_completness = float(line_list[6])
            bin_contamination = float(line_list[7])

            if bin_completness >= high_qual_threshold[0] and bin_contamination <= high_qual_threshold[1]:
                bin_status = "HIGH"
                bin_out_dir = high_dir
            elif bin_completness >= medium_qual_threshold[0] and bin_contamination <= medium_qual_threshold[1]:
                bin_status = "MEDIUM"
                bin_out_dir = medium_dir
            #
            bin_size = line_list[9]
            bin_nb_contig = line_list[11]
            bin_n50 = line_list[14]
            bin_longest_contig = line_list[18]
            #Get the stats
            OUT.write("{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\n".format(bin_id, bin_status, bin_completness, bin_contamination,  bin_size, bin_nb_contig, bin_n50, bin_longest_contig))

            if bin_status == "HIGH" or bin_status == "MEDIUM":
                run_exe("ln -s {}/all/{}.fa {}/{}.fa".format(binner_dir, bin_id, bin_out_dir, bin_id))
            
    FILE.close()
    OUT.close()
    
def checkm_analysis(assembly_dir, binner, nb_thread, high_qual_mags, medium_qual_mags):

    #Identify the correct suffix for check analysis
    suffix = "fa"
    if binner == "maxbin2":
        suffix="fasta"

    #Create the required directories
    binner_dir = assembly_dir + "/" + binner
    bin_dir = binner_dir + "/all"
    checkm_dir = binner_dir + "/checkm"
    create_dir(checkm_dir)

    #Run the checkm analysis
    eval_file = binner_dir + "/eval.dat"
    run_checkm(bin_dir, checkm_dir, suffix, nb_thread, eval_file)
    
    #Get the high and medium quality mags directories and file description
    identify_high_medium_bin(binner_dir, eval_file, high_qual_mags, medium_qual_mags)
    
    
    
def run_kraken2(assembly_dir, read1, read2, long_read, nb_thread, abundance_threshold):
    kraken_db = util_dir + "/../utils_db/minikraken2_v2_8GB"
    
    out_dir = assembly_dir + "/kraken2"
    create_dir(out_dir)
    #Short read
    out_file = out_dir + "/short_read.out"
    out_file_report = out_file + ".report"
    compress_format = "--gzip-compressed"
    if not os.path.exists(out_file_report):
        run_exe(util_dir + "/kraken2" + " --db " +  kraken_db + " --threads " + nb_thread + " --paired " + compress_format + " --output " + out_file + " --report " + out_file_report + " " + read1 + " " + read2)
    #
    #long read
    out_file = out_dir + "/long_read.out"
    out_file_report = out_file + ".report"
    compress_format = ""
    if not os.path.exists(out_file_report):
        run_exe(util_dir + "/kraken2" + " --db " +  kraken_db + " --threads " + nb_thread + " " + compress_format + " --output " + out_file + " --report " + out_file_report + " " + long_read)
    
    #Comapare the abundance profile
    compare_abundance_profile(out_dir, out_dir + "/short_read.out.report", out_dir + "/long_read.out.report", "S", abundance_threshold)
    compare_abundance_profile(out_dir, out_dir + "/short_read.out.report", out_dir + "/long_read.out.report", "G", abundance_threshold)
                
def compare_abundance_profile(out_dir, short_read_profile, long_read_profile, tax_level, abundance_threshold):
    tax_abundance_comparison = {}
    read_profile(short_read_profile, tax_level, abundance_threshold, tax_abundance_comparison, 0)
    read_profile(long_read_profile, tax_level, abundance_threshold, tax_abundance_comparison, 1)
    #
    OUT = open(out_dir + "/" + tax_level + "_abundance_comparison.txt", "w")
    OUT.write("Tax_name\tShort_read_abundance\tLong_read_abundance\n")
    for tax in tax_abundance_comparison:
        OUT.write("{}\t{}\t{}\n".format(tax, tax_abundance_comparison[tax][0], tax_abundance_comparison[tax][1]))
    OUT.close()
        
def read_profile(profile, tax_level, abundance_threshold, abundance_comparison, col):
    FILE = open(profile, "r")
    for line in FILE:
        #print line
        line_list = line.split("\t")
        tax = line_list[3]
        abundance = float(line_list[0].strip())
        tax_name = ((line_list[5].lstrip()).rstrip()).replace(" ", "_")
        if tax == tax_level and abundance > abundance_threshold:
            #print tax + " |" + abundance + "| |" + tax_name + "|\n"
            if tax_name not in abundance_comparison:
                abundance_comparison[tax_name] = {0:0, 1:0}
            abundance_comparison[tax_name][col] = abundance
    FILE.close()
    
def run_mash(all_binning_method, assembly_dir):
    mash_db = "/home/bertrandd/PROJECT_LINK/OPERA_LG/META_GENOMIC_HYBRID_ASSEMBLY/OPERA-MS-DEV/OPERA-MS/genomeDB_Sketch.msh";
    mash_exe = "/home/bertrandd/PROJECT_LINK/OPERA_LG/META_GENOMIC_HYBRID_ASSEMBLY/OPERA-MS-DEV/OPERA-MS/utils/mash"
    all_binning_method_array = all_binning_method.split(",")
    for binning_method in all_binning_method_array:
        binning_dir = assembly_dir + "/" + binning_method
        cmd = mash_exe +  " dist -p 1 -d 0.2 " + mash_db + " " + binning_dir + "/*fa* > " + binning_dir + "/mash.dist"
        run_exe(cmd)
        
def download_utils_db():
    mash_db = "/home/bertrandd/PROJECT_LINK/OPERA_LG/META_GENOMIC_HYBRID_ASSEMBLY/OPERA-MS-DEV/OPERA-MS/genomeDB_Sketch.msh";
    kraken_db = "/mnt/genomeDB/misc/softwareDB/kraken2/standard-20190108";


def read_taxonomy_file(genomes_dir, taxonomy, db_genome_dir, genome_list, genome_length):
    OUT_LIST = open(genome_list, "w")
    OUT_LENGTH = open(genome_length, "w")
    FILE = open(taxonomy, "r")
    line_list = {}
    tax_info = {}
    genome = ""
    species_name = ""
    for line in FILE:
        #print line
        line_list = (line.rstrip('\n')).split("\t")
        genome = line_list[0]
        tax_info = line_list[1].split(";")
        species_name = ""
        for t in tax_info:
            current_tax = t.split("__")
            if current_tax[0] == "s":
                species_name = current_tax[1].replace(" ", "_")
                
        if species_name == "":
            exit("Malformed taxonomy file: " + taxonomy + "\n" + line)
        else:
            #copy the file in the opera-ms-db directory
            novel_genome_name = db_genome_dir + "/" + species_name + "__" + genome  #Need to fix this !!!
            #Check for gzip file
            run_exe("cp {}/{} {}".format(genomes_dir, genome, novel_genome_name))
            OUT_LIST.write(novel_genome_name + "\n")
            #Write the length
            OUT_LENGTH.write("{}\t{}\n".format(novel_genome_name, "\t".join([str(x) for x in compute_genome_length(novel_genome_name)])))
    OUT_LENGTH.close()
    OUT_LIST.close()
    FILE.close()

def compute_genome_length(genome):
    res = [0, 0]
    with gzip.open(genome, "r") as FILE:
        for line in FILE:
            if not (line[0] == ">"):
                res[1] += (len(line)-1)
            else:
                res[0] += 1
    return res
        
def create_mash_sketch(genome_list, out_file, nb_thread):
    run_exe("{}/mash sketch -o {} -p {} -l {}".format(util_dir, out_file, nb_thread, genome_list)) #other potential parameters -k -s
    
def opera_ms_db(genomes_dir, taxonomy, db_name, nb_thread):
    #Create the output database directory
    create_dir(db_name)
    genome_db = db_name + "/genomes"
    create_dir(genome_db)
    
    #Read the taxonomy file
    #The genome name will be renamed according to the taxonomy file: SPECIES_NAME__GENOME_NAME
    genome_list = db_name + "/genomes_list.txt"
    genome_size = db_name + "/genomes_length.txt"
    read_taxonomy_file(genomes_dir, taxonomy, genome_db, genome_list, genome_size)
            
    #Create mash sketch
    create_mash_sketch(genome_list, db_name+"/genomes.msh", nb_thread)
            
    #Create 8Gb kraken db

    
def read_opera_ms_config_file(config_file):
    config_dict = {}
    with open(config_file, "r") as fp:
        for line in fp:
            line = line.split("#")[0]
            line = line.split()
            # if empty line
            if not line:
                continue
            config_dict[line[0]] = " ".join(line[1:])
    return config_dict


def is_good_quality(bin_status, mag_selected_qual):
    res = False 
    if bin_status.lower() == "high" or bin_status.lower() == mag_selected_qual:#If high quality or medium and mag_qual is medium the bin is used
        res = True
    return res

def get_sample_mags(conf, binner, mag_selected_qual, mag_out, mag_info):
    config_dict = read_opera_ms_config_file(conf)
    binner_dir = config_dict["OUTPUT_DIR"] + "/" + binner

    FILE = open(binner_dir + "/bin_info.txt", "r")
    for line in FILE:
        info = (line.rstrip('\n')).split("\t")
        bin_id = info[0]
        bin_status = info[1]
        if is_good_quality(bin_status, mag_selected_qual):
            mag_info[bin_id] = {"INFO":list(info),
                                "BEST_HIT_SPECIES":"NA",
                                "BEST_HIT_GENOME":"NA",
                                "BEST_HIT_DIST":1,
                                "STATUS":"KNOWN",
                                "NOVEL_SPECIES_ID":"NA"}
            try:
                run_exe("ln -s " +
                        binner_dir + "/" + bin_status.lower() + "_quality/" + bin_id + "." + get_binner_file_type(binner) +
                        " " +
                        mag_out + "/" + bin_id + ".fasta")
            except:
                pass

def get_mag_id(mag_path):
    return ((mag_path.split("/"))[-1]).replace(".fasta", "")

def get_ref_genome_name(ref_genome_path):
    return ((ref_genome_path.split("/"))[-1]).split("__")

def update_best_hit_status(mag_info, file_info):
    FILE = open(file_info, "r")
    for line in FILE:
        (ref_genome_path, mag_path, distance, pvalue, kmer_info) = (line.rstrip('\n')).split('\t')
        mag_id = get_mag_id(mag_path)
        ref_genome_name = get_ref_genome_name(ref_genome_path)
        #
        mag_info[mag_id]["BEST_HIT_SPECIES"] = ref_genome_name[0]
        mag_info[mag_id]["BEST_HIT_GENOME"] = ref_genome_name[1]
        mag_info[mag_id]["BEST_HIT_DIST"] = float(distance)


def update_novel_status(mag_info, file_info):
    FILE = open(file_info, "r")
    FILE.readline() #skip the header
    for line in FILE:
        (mag_id, cluster_id) = (line.rstrip('\n')).split('\t')
        mag_id = mag_id[1:-1]
        mag_info[mag_id]["STATUS"] = "NOVEL"
        mag_info[mag_id]["NOVEL_SPECIES_ID"] = "NS_" + cluster_id

def run_novel_species_analysis(ref_known_species, configs, binner, mag_qual, out):
    create_dir(out)
    mag_out=out + "/MAGs"
    create_dir(mag_out)
    
    #Get the required MAGS for each samples creat a soft link in out_mags and collect the MAGs info
    mag_info = {}
    for conf in configs:
        get_sample_mags(conf, binner, mag_qual, mag_out, mag_info)

    #Run the novel species analysis
    out_analysis = out+"/novel_species_analysis"
    if not os.path.exists(out_analysis+"/novel/cluster.tsv"):
        run_exe("python {}/../bin/novel_species_identification.py -s 1000 --ref {} --query {} --file_type {} --outdir {}".format(util_dir, ref_known_species, mag_out, "fasta", out_analysis))

    #Update the statistics about the analysis
    update_best_hit_status(mag_info, out_analysis+"/query_ref/min_hit.dat")
    update_novel_status(mag_info, out_analysis+"/novel/cluster.tsv")

    #Print the final info file
    OUT = open(out+"/MAGs_info.txt", "w")
    for mag in sorted(mag_info, key=lambda x: float(mag_info[x]["INFO"][2]), reverse=True):
        OUT.write(
            "\t".join(mag_info[mag]["INFO"]) + "\t" +
            mag_info[mag]["BEST_HIT_SPECIES"] + "\t" +
            mag_info[mag]["BEST_HIT_GENOME"] + "\t" +
            str(mag_info[mag]["BEST_HIT_DIST"]) + "\t" +
            mag_info[mag]["STATUS"] + "\t" +
            mag_info[mag]["NOVEL_SPECIES_ID"] + "\n")
                      
        
    
def main(args):
    
    command = args.command
    nb_thread = 0
    if command == "maxbin2" or command == "metabat2" or command == "checkm" or command == "mash" :
    
        #Parse the config file
        config_dict = read_opera_ms_config_file(args.config)
                        
        #Set the number of thread
        nb_thread = config_dict["NUM_PROCESSOR"]
        
        if args.thread != None:
            nb_thread = args.thread
        
        if command == "maxbin2" or command == "metabat2":
            sample_name = args.sample_name
            if sample_name == None:
                sample_name = config_dict["OUTPUT_DIR"].split("/")[-1]
            run_binner(command, sample_name, config_dict["OUTPUT_DIR"], config_dict["ILLUMINA_READ_1"], config_dict["ILLUMINA_READ_2"], nb_thread)

        elif command == "checkm":
            checkm_analysis(config_dict["OUTPUT_DIR"], args.binner, nb_thread, args.high_qual_mags, args.medium_qual_mags)

        elif command == "kraken2":
            abundance_threshold = 0.1
            if args.abundance_threshold != None:
                abundance_threshold = args.abundance_threshold
                run_kraken2(config_dict["OUTPUT_DIR"], config_dict["ILLUMINA_READ_1"], config_dict["ILLUMINA_READ_2"], config_dict["LONG_READ"], nb_thread, float(abundance_threshold))

        elif command == "mash":
            run_mash(mash, config_dict["OUTPUT_DIR"])

        elif command == "novel-species":
            print("TO DO")
    #Command without config file
    else:
        if command == "novel-species":
            run_novel_species_analysis(args.known_species, args.configs, args.binner, args.mags_qual, args.out)
            
        if command == "opera-ms-db":
            nb_thread = args.thread
            opera_ms_db(args.genomes_dir, args.taxonomy, args.db_name, nb_thread)
        
        elif command == "utils-db":
            print("TO DO")

        elif command == "check-install":
            print("TO DO")
        
if __name__ == "__main__":   

    parser = argparse.ArgumentParser()
    
    #group = parser.add_mutually_exclusive_group()
    #The type of software
    subparsers = parser.add_subparsers(help='commands', dest='command')
    #maxbin2
    maxbin_parser = subparsers.add_parser('maxbin2', parents=[config_parser.parser], help='Run MaxBin2')
    maxbin_parser.add_argument("-s", "--sample-name", help="Sample name [default OPERA-MS output directory]")
    
    #metabat2
    metabat_parser = subparsers.add_parser('metabat2', parents=[config_parser.parser], help='Run MetaBAT2')
    metabat_parser.add_argument("-s", "--sample-name", help="Sample name [default OPERA-MS output directory]")
    
    #kraken
    kraken_parser = subparsers.add_parser('kraken2', parents=[config_parser.parser], help='Run Kraken2 on the short and long reads and compare the abundance profiles')
    kraken_parser.add_argument("-a", "--abundance-threshold", default=0.1, help="Lower percentage abundance threshold [default 0.1]", type=int)
    
    #chechm
    checkm_parser = subparsers.add_parser('checkm', parents=[config_parser.parser], help='Run CheckM on a set of bins')
    checkm_parser._action_groups[-1].add_argument("-b", "--binner",  required=True, choices=["maxbin2", "metabat2", "opera_ms_cluster"])
    checkm_parser.add_argument("-H", "--high-qual-mags",  default="90,5", help = 'Completness and contamination values for high quality genomes (default: 90,5)', type=str)
    checkm_parser.add_argument("-M", "--medium-qual-mags",  default="50,10", help = 'Completness and contamination values for medium quality genomes (default: 50,10)', type=str)
    
    #mash
    #mash_parser = subparsers.add_parser('mash', parents=[config_parser.parser], help='Run Mash')
    
    #novel species
    novel_species_parser = subparsers.add_parser('novel-species', help='Run novel species identification')
    novel_species_parser._action_groups[-1].add_argument("-k", "--known-species",  required=True, help='Mash sketch of known species reference genomes')
    novel_species_parser._action_groups[-1].add_argument("-b", "--binner",  required=True, choices=["maxbin2", "metabat2", "opera_ms_cluster"])
    novel_species_parser._action_groups[-1].add_argument("-o", "--out",  required=True, help='Output directory')
    #
    novel_species_parser.add_argument('configs', metavar='C', nargs='+', help='Path to OPERA-MS configuration file(s)')
    #
    novel_species_parser.add_argument("-q", "--mags-qual", help='Quality of the MAGS used (default: high)', choices=["high", "medium"], default="high")
    novel_species_parser.add_argument("-c", "--cluster-threshold", help='Distance at which the genome will be clustered in the same species (default: 0.05)', default=0.05, type = float)
    
    #opera-db
    opera_db_parser = subparsers.add_parser('opera-ms-db', help='Create a OPERA-MS genome database')
    opera_db_parser._action_groups[-1].add_argument("-g", "--genomes-dir",  required=True, help='Directory that contains genome files')
    opera_db_parser._action_groups[-1].add_argument("-x", "--taxonomy",  required=True, help='Species name of each genomes')
    opera_db_parser._action_groups[-1].add_argument("-d", "--db-name",  required=True, help='Database name')
    opera_db_parser.add_argument("-t", "--thread", help='Number of threads [Default 2]')
        
    #utils-db
    utils_db_parser = subparsers.add_parser('utils_db', help='Download all the data base required by the utils software')

    check_install_parser = subparsers.add_parser('CHECK_DEPENDENCY', help='Check which OPERA-MS-UTILS software are functional in the current system')
    
    args=parser.parse_args()
    print(args)
    
    #print(args.checkm)#print(args.metabat2)
    main(args)
