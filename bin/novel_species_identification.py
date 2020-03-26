import subprocess
import argparse
import os
import sys

script_dir = (os.path.dirname(os.path.realpath(__file__)))

def run_exe(cmd):
    run = 1
    print(cmd)
    if run:
        return subprocess.check_output(cmd, shell=True)
        

def compute_mash_dist(script_dir, thread, ref_sketch, query_sketch,  query_ref_dist_file):
    if not os.path.exists(query_ref_dist_file):
        run_exe("{}/../utils/mash dist -p {} -d 0.22 {} {} > {}".format(script_dir, thread, ref_sketch, query_sketch,  query_ref_dist_file))   
        #run_exe("{}/../utils/mash dist -p {} -d 0.3 {} {} > {}".format(script_dir, thread, ref_sketch, query_sketch,  query_ref_dist_file))   
def get_sketch(query_files, thread, sketch_size, kmer_size, outdir, file_type, sketch_name): 

    sketch = "{}/{}".format(outdir, sketch_name)
    if not os.path.exists(sketch+".msh"):
        run_exe("mkdir -p {}".format(outdir))    
        run_exe("{}/../utils/mash sketch -p {} -k {} -s {} -o {} {}  > {}/{}.out 2> {}/{}.err ".format(script_dir, thread, kmer_size, sketch_size, sketch, query_files, outdir, sketch_name, outdir, sketch_name))
    return sketch+".msh"


def get_novel_sequence(mag_dir, dist_file, outdir):
    
    dict_species = {} # contains the shortest dist for each new species      
    with open(dist_file, "r") as f:
        for line in f:
            dist = float(line.split()[2])                                                    
            species_key = line.split()[1]            
            try:
                #get smallest distance for that species
                if dist < dict_species[species_key][1]:                                              
                    dict_species[species_key] = [line, dist]                                         
            except KeyError:                                                                         
                dict_species[species_key] = [line, dist]
    
    novel_sequence = "{}/novel_sequence.dat".format(outdir)
    min_hit = "{}/min_hit.dat".format(outdir)
    novel_seq_files = ""
    with open(novel_sequence, "w") as fp, open(min_hit, "w") as mh:        
        for key in dict_species:
            mh.write(dict_species[key][0])
            if float(dict_species[key][1]) > 0.05:
                line = "{}\n".format(key)
                fp.write(line)
                novel_seq_files = novel_seq_files + line.strip() + " "
        # if the mag bin is not presented in distance file after mash, add to novel_sequence
        print(dict_species)
        for mag_bin in os.listdir(mag_dir):
            if os.path.join(mag_dir, mag_bin) not in dict_species:
                print("came to here")
                fp.write(os.path.join(mag_dir, mag_bin) + "\n")
                novel_seq_files = novel_seq_files + os.path.join(mag_dir, mag_bin)  + " "
                mh.write("{}\t{}\t{}\t{}\t{}\n".format("UNKOWN", os.path.join(mag_dir, mag_bin), "1", "NA", "NA"))
    return (novel_sequence, novel_seq_files)


def get_cluster(script_dir, hclust_thres, dist_file, outdir, file_type):
    dist_matrix = get_matrix(dist_file, len(file_type), outdir)
    cluster_file = outdir + "/cluster.tsv"
    try:
        os.remove(cluster_file)
    except:
        pass
    cmd = "Rscript --vanilla {}/mags_clustering.r {} {} {}".format(script_dir, dist_matrix,  hclust_thres, cluster_file)
    run_exe(cmd)

def get_matrix(dist_file, extension_len, outdir):
    
    matrix = {}
    count = 0
    with open(dist_file, "r") as f:
        for line in f:
            
            ID = line.split()
            ID1 = ID[0].split("/")[-1][:-(extension_len + 1)].strip()
            ID2 = ID[1].split("/")[-1][:-(extension_len + 1)].strip()
            dist = ID[2]
            #print(ID1)
            #print(ID2)
            try:                
                matrix[ID1].update({ID2 : dist})
            except KeyError:
                matrix[ID1] = {ID2 : dist}
            try:                
                matrix[ID2].update({ID1 : dist})
            except KeyError:
                matrix[ID2] = {ID1 : dist}
                    
        dimension = 0
        for key1 in matrix:
            dimension += 1
            for key2 in matrix:            
                if key2 not in matrix[key1]:
                    matrix[key1][key2] = 1.0
                      
        print("generating {} x  {} distance matrix for clustering...".format(dimension, dimension))

        
        dist_matrix = outdir + "/dist_matrix.dat"
        with open(dist_matrix, 'w') as f:
            f.write('\t')
            for key in sorted(matrix.iterkeys()):
                f.write(key + '\t')
            f.write('\n')        
            for key in sorted(matrix.iterkeys()):
                f.write(key + '\t')
                
                for key2 in sorted(matrix.iterkeys()):
                    dist = matrix[key][key2]
                    f.write(str(dist) + '\t')         
                f.write('\n')
    return dist_matrix


def main(args):
    ref_sketch = args.ref
    query_dir = args.query
    sketch_size = args.sketch
    kmer_size = args.kmer
    thread = args.threads
    outdir = args.outdir
    file_type = args.file_type
    hclust_thres = args.hclust_thres
    
    try:
        os.mkdir(outdir)
    except:
        pass
    
    #Create the selected MAGs  mash sketch
    cmd = "ls {}/*{}".format(query_dir, file_type)
    temp_query_files = run_exe(cmd).split("\n")    
    all_query_dict = dict.fromkeys(temp_query_files, 1)
    
    query_ref_outdir = outdir + "/query_ref/"
    sketch_name = "query_sketch"
    query_files = "{}/*{}".format(query_dir, file_type)
    
    #create mash sketch
    query_sketch = get_sketch(query_files, thread, sketch_size, kmer_size, query_ref_outdir, file_type, sketch_name)
    
    #Compute the mash distance between the mags and reference genomes
    query_ref_dist_file = query_ref_outdir + "/query_ref_dist.dat"
    compute_mash_dist(script_dir, thread, ref_sketch, query_sketch,  query_ref_dist_file)
    
    #generate the distance file and identify the novel genome based on distance to know genome < 0.05
    #PROBLEM: genome without distance to known ref genome are excluded
    novel_sequence, novel_seq_files = get_novel_sequence(query_dir, query_ref_dist_file, query_ref_outdir)
    
    get_cluster(script_dir, 0.05, query_ref_dist_file, query_ref_outdir, file_type)
    
    # find novel genome clusters to identify the novel species (a species is a cluster of novel genome)
    print(novel_sequence)
    novel_sketch_name = "novel_sketch"
    novel_outdir = outdir + "/novel/"
    novel_sketch = get_sketch(novel_seq_files, thread, sketch_size, kmer_size, novel_outdir, file_type, novel_sketch_name)
    novel_dist_file = novel_outdir + "/novel_dist.dat"
    compute_mash_dist(script_dir, thread, novel_sketch, novel_sketch,  novel_dist_file)

    #generate matrix
    #PROBLEM:  if only 1 genome the clustering crash
    get_cluster(script_dir, 0.05, novel_dist_file, novel_outdir, file_type)

    
if __name__ == "__main__":
    parser = argparse.ArgumentParser("determine novel sequence from given database")

    mandatory = parser.add_argument_group("mandatory arguments")

    mandatory.add_argument("-r", "--ref",
                           required=True,
                           help="reference mash sketch")
    mandatory.add_argument("-q", "--query",
                           required=True,
                           help="query files directory")
    mandatory.add_argument("-o", "--outdir",
                           required=True,
                           help="output directory")
    mandatory.add_argument("-f", "--file_type",
                           required=True,
                           help="query file type, fastq, fasta, fq or fa")
    
    parser.add_argument("-k", "--kmer",
                        default = 21,
                        type = int,
                        help="mash sketch kmer size")
    parser.add_argument("-s", "--sketch",
                        default = 10000,
                        type = int,
                        help="mash sketch size")
    parser.add_argument("-c", "--hclust_thres",
                        default = 0.05,
                        type = float,
                        help="cutoff for hierachical clustering, default cutoff at 0.05")

    parser.add_argument("-t", "--threads",
                        default = 1,
                        type = int,
                        help="number of threads used")
    
    args=parser.parse_args()
    
    main(args)
