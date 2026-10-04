Initial Setup
=========

Please read the main ReadMe.md file for context as well as the documentation of the current NPPES PUF file release in ./docs/

First create a .gitignore that excludes the ./working_data/ directory and standard cruft files for windows/linux/OSX and typically python exclusions. 

Under the working directory there will be a zip file that is a current download of the monthly zip file from https://download.cms.gov/nppes/NPI_Files.html 

There should be a script called Step10_current_nppes_downloader.py that goes to https://download.cms.gov/nppes/NPI_Files.html and searches for a file in the format of https://download.cms.gov/nppes/NPPES_Data_Dissemination_September_2026_V2.zip and downloads it into ./working_data/ and unzips the file. 

Eventually there will be a download link for the NPD managed files.. but for now, you will find a file called ./mock_data/npd_nppes_file_mockup_initial.csv

This will will contain a handful of records that simulate the eventual NDP export in the new V3 NPPES data format. 

Then build a script called Step30_merge_puf_files.py which will load the NPD version into memory, and then stream the old NPPES main file, and export it into ./working_data/output.csv  

./working_data/output.csv should be in the new V3 version of the NPPES PUF file with the additional columns as documented in the ReadMe.md . Each line in the new file should contain the defaults for those new columns, except where the column is managed by NPD (and is therefore in ./mock_data/npd_nppes_file_mockup_initial.csv) All of these NPI rows should be copied to the new output file in exactly the same order that they are copied to the new folder. The NPIs in the output file should retain the exact same order as they do in the source NPPES file. If there are additional NPIs in the NPD file that do not appear in the original NPPES PUF file, place them at the end of the file. 

Then you need to write a Step40_test_merge.py file that uses InLaw  https://pypi.org/project/inlaw/ to make a few tests of the data. Use pandas to make a data frame of the old and new files as needed to run the InLaw tests. Please ensure that your scripts do not overload the memory of a standard 10 GB ram laptop. The tests should include: 

* There are more than 9,700,000 NPIs in the resulting output file but less than 11,000,000
* The order of the rows (as determined by the NPI identifier that is in the first column) of the old NPPES PUf and the output file are identical, except that the output PUF file could have more rows in any order.
* There are no repeating NPI records

Step50_rezip.py should take the output.csv, rename it to the same name as the incoming CSV file and then zip up the new but with V3 in the place of V2 in the zip filename. The V2 and V3 zip files should appear next to each other in the ./working_data/ directory

Please make a go.py script that runs all of the Steps and calculates filenames (etc) to pass to the CLI arguements to the other steps. 

