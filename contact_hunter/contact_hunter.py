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

##convert coordinates to locus - bins
def preproc_data(locus_file,res): 
    locus_coord=pd.read_csv(locus_file,sep='\t',header=None)    
    locus_coord.columns=['chrom','start']
    locus_coord['start']=(locus_coord['start']/res).astype(int)
    Locus=locus_coord.drop_duplicates(['chrom','start'])
    
    return(Locus)

##write obs/exp maps to txt.files
def norm(cool_file,ch,res):
    ff=cooler.Cooler(cool_file)
    s=ff.matrix(balance=True).fetch(ch)
    D=np.zeros(len(s))
    for i in range (len(s)):
        D[i]=np.nanmean(s.diagonal(i))
     
    A=np.zeros((len(s),len(s)))
    n=len(s)
    for i in range (len(s)):
        row_id=np.arange(0,(n-i))
        col_id=np.arange(i,n)

        if D[i]!=0:
            A[row_id,col_id]=s[row_id,col_id]/D[i]
            A[col_id,row_id]=s[col_id,row_id]/D[i]

    return(A)



##create array of profiles of interactions for bins with SNP +- predefined distance
def create_profiles(hic_prepared,n,locus_list,ch):
        
    locus_tmp=locus_list.loc[locus_list['chrom']==ch]
    locus_tmp=locus_tmp.sort_values(['chrom','start'])
    locus_tmp=locus_tmp.reset_index(drop=True)
        
    col_idx = locus_tmp['start']+n
    col_idx_rep = np.repeat(col_idx, 2*n+1)

    row_inc = np.arange(-n, n+1)
    row_inc_tile = np.tile(row_inc, len(col_idx))
    row_idx = col_idx_rep + row_inc_tile
    
    profiles=hic_prepared[row_idx, col_idx_rep][:, np.newaxis].reshape(len(col_idx), -1)  
    
    return(profiles)
 
##calculate p-values by comparison with profiles for background SNP
def pvalue_calculation(profiles,my_profiles,n):
    my_p=np.zeros(np.shape(my_profiles))
    for i in np.append(np.arange(0,n-1),np.arange(n+2,2*n+1)):
        prof=profiles[:,i]
        prof=prof[~np.isnan(prof)]
        q95=np.percentile(prof,q=[95])
        prof=prof[(prof>0)&(prof<=q95)]
        if (len(prof))==0:
            raise Exception('bin size is too small, try increase it')
        s1,loc1,scale1=scipy.stats.lognorm.fit(prof)
        w=scipy.stats.lognorm(s=s1,loc=loc1,scale=scale1)
        my_p[:,i]=1-w.cdf(x=my_profiles[:,i]) 

        

    return(my_p)



def sign_contact(hic,locus_background_coord_preproc,locus_tested_preproc,res,ch,dist): 
    
    n=int(dist/res)
    m=hic
    m=np.pad(m,n)
    back_profiles=create_profiles(m,n,locus_background_coord_preproc,ch)
    my_profiles=create_profiles(m,n,locus_tested_preproc,ch)
    pval=pvalue_calculation(back_profiles,my_profiles,n)
    
    return(pval)    



def postprocess_prepare(locus_tested_file,res):
    my_locus=pd.read_csv(locus_tested_file,sep='\t',header=None)
    my_locus[2]=my_locus[0].astype(str)+':'+my_locus[1].astype(str)
    my_locus[1]=(my_locus[1]/res).astype(int)
    my_locus=my_locus.groupby([0,1])[2].apply(list).reset_index()
    my_locus.sort_values([0,1],inplace=True)
    return(my_locus)


    
## fdr
def qvalue_calculation(pval_table,fdr):
    
    qval_table=np.zeros(np.shape(pval_table))
    for i in range(np.shape(pval_table)[1]):
        pval=pval_table[:,i]
        pval=pval[pval!=0]
        pval=pval[~(np.isnan(pval))]
        L=len(pval)
        rank=np.array([sorted(pval).index(x) for x in pval])+1
        u=pd.DataFrame({'pval':pval,'rank':rank,'qval':rank*fdr/L})
        u=u.loc[u.pval<u.qval]
        if len(u)>0:
            critical_q=max(u.pval)
        else:
            critical_q=-1

        qval_table[:,i]=critical_q 
    
    return(qval_table)


def significant_contacts_average_heatmap(norm_map,sign_contact_table,chrom,res,d=10):

    a=sign_contact_table[['chr','bin_to_test','interacting_bin_coord']]
    a.columns=[0,1,2]
    a=a.loc[abs(a[2]-a[1])>2*res]
    s=norm_map
    s=np.pad(s,d)
    w=a[a[0]==chrom]
    w.reset_index(drop=True,inplace=True)
    D=np.zeros((d*2+1,d*2+1,len(w)))
    k=0
    for i in range(len(w)):
        x=(w.iloc[i][1]/res).astype(int)
        y=(w.iloc[i][2]/res).astype(int)
        z=s[x:x+2*d+1,y:y+2*d+1]
        D[:,:,k]=z
        k+=1
    return(D)

def post_processing_for_sign_contacts(pval_array,locus_tested_spec_file,res,dist,fdr,ch):# 
    
    n=int(dist/res)
    my_locus=locus_tested_spec_file.copy()
    my_locus_tmp=my_locus.loc[my_locus[0]==ch]
    pval_table=pval_array
    qval_table=qvalue_calculation(pval_table,fdr)
    snp_significant_contacts=pd.DataFrame()    
    for i in range(len(my_locus_tmp)):
        interacting_locus_coordinates=np.arange(my_locus_tmp.iloc[i][1]-n,my_locus_tmp.iloc[i][1]+n+1,1)*res

        df_tmp=pd.DataFrame({'chr':[my_locus_tmp.iloc[i][0]]*(2*n+1),
                             'bin_to_test':[my_locus_tmp.iloc[i][1]*res]*(2*n+1),
                             'list_of_initial_loci':[my_locus_tmp.iloc[i][2]]*(2*n+1),
                             'interacting_bin_coord':interacting_locus_coordinates,
                             'p-val':pval_table[i],
                             'p-value_critical':qval_table[i]})

        snp_significant_contacts=pd.concat([snp_significant_contacts, df_tmp.loc[(df_tmp['p-val']>0)&(df_tmp['p-val']<=df_tmp['p-value_critical'])]])

    return(snp_significant_contacts[['chr','bin_to_test','list_of_initial_loci','interacting_bin_coord','p-val']])       
            
        


def create_final_table(cool,background_locus,tested_locus,res,dist,fdr,ch):
    file=norm(cool,ch,res)
    back_locus=preproc_data(background_locus,res)
    test_locus=preproc_data(tested_locus,res)
    sign_cont_pval=sign_contact(file,
                            back_locus,
                            test_locus,
                            res,ch,dist)
    print(ch)
    locus_test_spec_file=postprocess_prepare(tested_locus,res)
    sign_cont_qval=post_processing_for_sign_contacts(sign_cont_pval,locus_test_spec_file,res,dist,fdr,ch)
    data_for_heatmap=significant_contacts_average_heatmap(file,sign_cont_qval,ch,res,d=10)
    return(sign_cont_qval,data_for_heatmap)



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

def bad_distance(cool,distance,chrom):
    c=cooler.Cooler(cool)
    d=int(np.round(min(c.chromsizes[chrom])/4,-int(np.log10(min(c.chromsizes[chrom]/4)))))
    if  (d<distance):
        return(1)

def get_contacts_cli(cool,background_loci,tested_loci,res,dist,chromosomes,fdr,heatmap_generate):
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

    return(df,plot)

def plot_heatmap(data,path_to_image):
    plt.imshow(np.log(np.nanmean(data,axis=2)+0.01),cmap='coolwarm')
    plt.xticks([0,10,20],[-10,0,10])
    plt.yticks([0,10,20],[-10,0,10])
    plt.xlabel('distance, bins')
    plt.colorbar(label='FC, obs/exp')
    plt.title('average heatmap\n around significant contacts')
    plt.savefig(path_to_image)
#######################################

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='The program identifies significant contacts for provided genomic regions across predefined distance. The method was borrowed from the paper  DOI:10.1038/nature19847 (Won et al 2016) with a small difference - significant contacts are detected for normalized Hi-C maps (obs/exp). Parameters of the tool were tuned to generate list of significant contacts for regions containing SNP in human genome. SNPs to be tested are credible SNP (after CAVIAR/FINEMAP), background SNPs are all SNPs obtained by GWAS. The tool is suitable to obtain significant contacts for TSSs too, but another background should be provided. Performance on other species or features (e.g. midpoints of ATAC-seq or ChIP-seq peaks) should be tested at first.',formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("COOL_PATH", help="path to cool file")
    parser.add_argument("BACKGROUND_LOCI", help="path to tab-delimited file with coordinates of background regions (points), should not contain header, 2 filds are expected: chrom, start")
    parser.add_argument("LOCI_TO_TEST", help="path to a file with loci of interes, same format as for background regions file")
    parser.add_argument("RES", type=int,help="resolution, dependes on the data quality (e.g. 5000-10000 for mammalian Hi-C maps of good quality, 20000-25000 for worse quality)")
    parser.add_argument('DIST',type=int,help="distance from loci of interes (in bp), constraining the field of significant contacts search (e.g. 5000000 for mammalian genome)")
    parser.add_argument('RESULTS_FILE', help="path to a file with significant contacts")
    parser.add_argument("--chr",default='all',help="list of chromosomes to be included, e.g. ['chr1','chr2']; if not specified inspects all the chromosomes")
    parser.add_argument("--fdr",default=0.01,type=float,help="false discovery rate")
    parser.add_argument("--heatmap_generate",action="store_true",default=False, help='plot an average heatmap for significant contacts and save it to the directory with the tested loci file')
    args = parser.parse_args()
    config = vars(args)
    print('Hello! The calculations may take a while.')
    df=get_contacts_cli(config["COOL_PATH"],config["BACKGROUND_LOCI"],config["LOCI_TO_TEST"],config["RES"],config['DIST'],config['chr'],config['fdr'],config['heatmap_generate'])
    df[0].to_csv(config['RESULTS_FILE'],index=None,sep='\t')
    if config['heatmap_generate']:
        path=os.path.abspath(config["LOCI_TO_TEST"])
        path=path.split('/')
        path='/'.join(path[:-1])
        plot_heatmap(df[1],"%s/heatmap_for_significant_contacts.png"%path)
