# NPD NPPES PUF Merge

Script to merge the NPPES and NPD versions of the NPPES PUF File.
Results in a single NPPES PUF that uses the v3 of the PUF.

The [National Provider Directory](https://directory.cms.gov)(NPD) url: https://directory.cms.gov is the system that will soon replace NPPES for the management of NPI records. In order to ensure a smooth transition between the two systems, the NPPES PUF will be modified to support the transition, as well as to support new features of the NPI management process under NPD. 

## Repo Contents

A script which accepts a zip file (or a CSV) of the main NPPES file, alongside a V3 Formatted version of the NPD PUF.
And outputs a V3 Formatted PUF. 

### Pipeline

| Script | Purpose |
| --- | --- |
| `go.py` | Runs every step below, working out the filenames to pass between them. |
| `Step10_current_nppes_downloader.py` | Finds the current monthly zip on [the CMS NPI Files page](https://download.cms.gov/nppes/NPI_Files.html), downloads it into `./working_data/` and unzips it. |
| `Step30_merge_puf_files.py` | Streams the NPPES main file and overlays the NPD managed records, writing `./working_data/output.csv` in the V3 format. |
| `Step40_test_merge.py` | Validates the merged file using [InLaw](https://pypi.org/project/inlaw/) / Great Expectations. |
| `Step50_rezip.py` | Renames `output.csv` back to the incoming CSV name and zips it as `..._V3.zip`, next to the `..._V2.zip`. |

Supporting modules:

| Script | Purpose |
| --- | --- |
| `nppes_v3.py` | Shared definition of the V3 columns, defaults and column offsets. |
| `make_mock_npd_file.py` | Regenerates `./mock_data/npd_nppes_file_mockup_initial.csv`. |
| `make_test_fixture.py` | Builds a small synthetic NPPES zip so the pipeline can be tested without a 1.1 GB download. |

### Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Full run: download, merge, validate and re-zip
./go.py

# Re-run against an already downloaded file
./go.py --skip-download
```

To exercise the pipeline without downloading the real monthly file:

```bash
python make_test_fixture.py --rows 5000
python go.py --skip-download --min-npis 4000 --max-npis 6000
```

### Validation

`Step40_test_merge.py` stages just the NPI column of the old and new files into
a local DuckDB database and then runs these InLaw tests:

* The output file has more than 9,700,000 and fewer than 11,000,000 NPIs.
* Every NPI from the source NPPES PUF is still present.
* The shared NPIs appear in the same relative order as the source NPPES PUF
  (the output may contain extra rows anywhere).
* There are no repeating NPI records.

Memory use is kept well inside a 10 GB laptop: the merge streams row by row
(~18 MB peak) and the validation pushes all comparison work down into DuckDB
(~420 MB peak), which spills to disk rather than RAM.

> **Note on the `inlaw` dependency.** `inlaw>=0.2.0` is required. Version 0.1.0
> installed its modules under a top level `src` package rather than `inlaw`, and
> its `sql_to_gx_df()` helper called `context.sources`, which was removed in
> Great Expectations 1.x. Both are fixed in 0.2.0, which also renames the test
> `run(engine, config=...)` parameter to `settings=` (`config=` still works but
> is deprecated).

### Caveats

* The NPD download link does not exist yet, so the merge reads the mock file in
  `./mock_data/`. Two of its three NPIs are real and active, so they exercise the
  replace path; the third (`1234567893`) is synthetic and absent from NPPES, so it
  exercises the append-at-end path.
* FaCeT normalisation is represented by pre-normalised values in the mock file.
  No FaCeT normalisation is performed at merge time, because only NPD managed
  records carry these improvements and they arrive already normalised.

## V3 NPPES File Format

### Additional columns

The following additional columns are added to the end of the main nppes file

* npi_managed_by = only two string options “npd” or “nppes”. Default is “nppes”
* npi_activation_status = ‘active’ / ‘deactive’ (and future values of ‘soon_to_be_deactivated’). Default value mirrors activation status of the current record.
* npi_activation_change_reason_list = field containing a pipe-delimited list of reasons what justifies a future change. Could include ‘Data Out of Date’, ‘Verification Required’, or simply ‘Login for specific message’ etc etc. Default value is blank
* npi_activation_future_change_date = the date which a field might change, default value of ‘0000-00-00’ for all values for now. 
* npi_fhir_url = an https link to the FHIR API record for the NPI

### Data Improvements

For the time being only data managed by NPD (npi_managed_by=npd) will contain these data improvements. It is an open question about whether these data improvements will be back-ported to NPPES NPI managed records.

The NPD (v3) version of the NPPES PUF has been modified to be compatible with the 

* Employer Identification Number (EIN) - modified to point to the uuid of the FHIR organization corresponding to the EIN of the legal entity in question
* Provider Credential Text - normalized with [FaCeT](https://github.com/ftrotter-gov/FaCeT) and moved to a pipe-sub-delimited list of credentials
* Provider Other Credential Text - normalized with [FaCeT](https://github.com/ftrotter-gov/FaCeT) and moved to a pipe-sub-delimited list of credentials
* Authorized Official Credential Text - normalized with [FaCeT](https://github.com/ftrotter-gov/FaCeT) and moved to a pipe-sub-delimited list of credentials
* The Identifier Data - The Identifier data has been dramatically reduced. The original intent of the identifiers system was to map legacy identifiers to the NPI. There are a handful of legitimate use cases for these mappings (Medicaid IDs in some cases), that will be maintained, but on balance the identifier data is a source of cruft and will be mostly removed from future versions of the file as we retire the identifier mapping functionality as no-longer nessecary. 

#### Normalization with FaCeT

[FaCeT](https://github.com/ftrotter-gov/FaCeT) is a normalized list of clinical and clinical-adjacent credentials. Using this allows for the correction of NPPES credentials into a reliable format. Currently these credentials are mere assertions. In the future, NPD will begin to conduct some form of credential verification. For the time being, credentials will be consistently expressed using FaCeT representations. 

For instance, the following NPPES entered credential values will be converted as: 

* "M.D. PHd" -> " MD | PHD "
* "M. D phd" -> " MD | PHD "
* "M. D. P.H.D" -> " MD | PHD "

Please see [The MD Problem in NPPES](https://www.fredtrotter.com/the-md-problem-in-nppes/) for discussion about the issues with the previous approach. 



## Policies

### Open Source Policy

We adhere to the [CMS Open Source Policy](https://github.com/CMSGov/cms-open-source-policy). If you have any questions, just [shoot us an email](mailto:opensource@cms.hhs.gov).

### Security and Responsible Disclosure Policy

_Submit a vulnerability:_ Vulnerability reports can be submitted through [Bugcrowd](https://bugcrowd.com/cms-vdp). Reports may be submitted anonymously. If you share contact information, we will acknowledge receipt of your report within 3 business days.

### Software Bill of Materials (SBOM)

A Software Bill of Materials (SBOM) is a formal record containing the details and supply chain relationships of various components used in building software.

In the spirit of [Executive Order 14028 - Improving the Nation's Cyber Security](https://www.gsa.gov/technology/it-contract-vehicles-and-purchasing-programs/information-technology-category/it-security/executive-order-14028), a SBOM for this repository is provided here: https://github.com/{{ cookiecutter.project_org }}/{{ cookiecutter.project_repo_name }}/network/dependencies.

For more information and resources about SBOMs, visit: https://www.cisa.gov/sbom.

## Public domain

This project is in the public domain within the United States, and copyright and related rights in the work worldwide are waived through the [CC0 1.0 Universal public domain dedication](https://creativecommons.org/publicdomain/zero/1.0/) as indicated in [LICENSE](LICENSE).

All contributions to this project will be released under the CC0 dedication. By submitting a pull request or issue, you are agreeing to comply with this waiver of copyright interest.
