import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()


setuptools.setup(
     name='contact_hunter',  
     version='0.1.0',
     python_requires=">=3.6.0",
     author="Anna Kononkova",
     author_email="a.kononkova@yandex.ru"
     description="A tool to obtain significant Hi-C contacts for a particular set of loci",
     packages=setuptools.find_packages(),
     url="https://github.com/Khrameeva-Lab/contact-hunter",
     long_description=long_description,
     long_description_content_type="text/markdown",

     classifiers=[
         'Intended Audience :: Science/Research',         
         "Programming Language :: Python :: 3",
         "License :: OSI Approved :: GPLv3 License",
         "Operating System :: OS Independent",
     ],

install_requires=['asciitree>=0.3.3',
'cached-property>=1.5.2',
'certifi>=2021.5.30',
'click>=8.0.4',
'cooler>=0.8.11',
'cycler>=0.11.0',
'cytoolz>=0.10.1',
'dill>=0.3.4',
'h5py>=3.1.0',
'importlib-metadata>=4.8.3',
'kiwisolver>=1.3.1',
'matplotlib>=3.3.4',
'multiprocess>=0.70.12.2',
'numpy>=1.19.5',
'pandas>=1.1.5',
'Pillow>=8.4.0',
'pyfaidx>=0.7.0',
'pypairix>=0.3.7',
'pyparsing>=3.0.9',
'python-dateutil>=2.8.2',
'pytz>=2022.1',
'PyYAML>=6.0',
'scipy>=1.5.4',
'simplejson>=3.17.6',
'six>=1.16.0',
'toolz>=0.11.2',
'typing_extensions>=4.1.1',
'zipp>=3.6.0'],

entry_points = {
        'console_scripts': ['contact_hunter=contact_hunter.cli:main'],
    }

 )
