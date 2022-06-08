import pandas as pd
import numpy as np
import scipy
import cooler
import multiprocess
from multiprocess import Pool
from functools import partial
from scipy import stats
import warnings
import  sys
import os
import argparse
import matplotlib.pyplot as plt
import gc

from contact_hunter.utils import (
     preproc_data,norm,create_profiles,pvalue_calculation,sign_contact,postprocess_prepare,
     qvalue_calculation,bad_distance,plot_heatmap,significant_contacts_average_heatmap,
     post_processing_for_sign_contacts,create_final_table,get_contacts_cli)


def get_contacts(cool,background_loci,tested_loci,res,dist,fdr,heatmap_generate,chromosomes='all'):

    """
    The program identifies significant contacts for provided genomic regions across predefined distance. The method is borrowed from the paper  DOI:10.1038/nature19847 (Won et al 2016) with a  small difference - contatcs are investigated for normalized Hi-C maps (obs/exp). Parameters of the tool are tuned to generate list of significant contacts for regions containing SNP in human genome. SNPs to be tested are credible SNP (after CAVIAR/FINEMAP), background SNPs are all SNPs from GWAS.  The tool is suitable to obtain significant contacts for TSSs too, but another background should be provided.  Performance on another data (features, species) should be tested at first.


    type cool: str
    description: path to cool-file

    type background_loci: str
    description: path to a tab-delimited file with background loci coordinates, should contain 2 columns - chrom, start; there should not be a header 

    type tested_loci: str
    description:  path to a tab-delimited file with tested loci coordinates, should contain 2 columns - chrom, start; there should not be a header

    type res: int
    description: resolution of Hi-C map

    type dist: int
    description: distance from locus, limiting an area of significant contacts search, for human genome 5MB is recommended

    type fdr: float
    description: Benjamini–Hochberg correction

    type plot_generate: boolean
    description plot_generate: generate or skip  average obs/exp Hi-C map  for significant contacts, this is some kind of quality control, serves to evaluate offhand whether significant contacts in general are pronounced  enough
    """
    c=cooler.Cooler(cool)
    warnings.filterwarnings("ignore", category=RuntimeWarning) 

    
    coord_background=pd.read_csv(background_loci,sep='\t',header=None)    
    coord_to_test=pd.read_csv(tested_loci,sep='\t',header=None)  
 
    if chromosomes=='all':   
        chroms=list(set(coord_background[0])&set(coord_to_test[0]))
    else:
        chroms=list(set(coord_background[0])&set(coord_to_test[0])&set(chromosomes))

    del(coord_background)
    gc.collect()

    bd=bad_distance(cool,dist,chroms)
    if bd:
        return('the distance for contacts identification is too large: reduce distance, exclude contigs and chrM from a file with loci to be tested (if they present there)')

    pool_obj = multiprocess.Pool(min(multiprocess.cpu_count()-2,len(chroms)))
    func = partial(create_final_table,cool,background_loci,tested_loci,res,dist,fdr)
    results = [pool_obj.apply_async(func,args=(i,)) for i in chroms]
    
    try:
        for result in results:
            result.get()[0]
    except:
        pool_obj.terminate()
        print("error")

    pool_obj.close()
    pool_obj.join()

    df=pd.DataFrame()
    plot=np.zeros((np.shape(results[0].get()[1])[0:2]+(1,)))

    for result in results:
        df=pd.concat([df,result.get()[0]])
        plot=np.dstack([plot,result.get()[1]])
    if heatmap_generate:
        plt.imshow(np.log(np.nanmean(plot,axis=2)+0.01),cmap='coolwarm')
        plt.xticks([0,10,20],[-10,0,10])
        plt.yticks([0,10,20],[-10,0,10])
        plt.xlabel('distance, bins')
        plt.colorbar(label='FC, obs/exp')
        plt.title('average heatmap\n around significant contacts')

    return(df)

