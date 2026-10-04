# NPD NPPES PUF Merge

Script to merge the NPPES and NPD versions of the NPPES PUF File.
Results in a single NPPES PUF that uses the v3 of the PUF.

The [National Provider Directory](https://directory.cms.gov)(NPD) url: https://directory.cms.gov is the system that will soon replace NPPES for the management of NPI records. In order to ensure a smooth transition between the two systems, the NPPES PUF will be modified to support the transition, as well as to support new features of the NPI management process under NPD. 

## Repo Contents

A script which accepts a zip file (or a CSV) of the main NPPES file, alongside a V3 Formatted version of the NPD PUF.
And outputs a V3 Formatted PUF. 

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
