<img src="https://data.source.coop/harvard-lil/gov-data/docs/LIL_HLSL_logos.png" alt="Harvard Law School Library Innovation Lab logo"/>

This is a mirror of all data files archived from [Data.gov](https://data.gov) between November 19, 2024 and February 6, 2025. The data can be browsed and searched at [Data.gov Archive Search](https://lil.law.harvard.edu/data-gov-archive/).

This repository is maintained by the [Public Data Project](https://lil.law.harvard.edu/our-work/public-data-project/), part of the [Library Innovation Lab](https://lil.law.harvard.edu) at Harvard Law School Library.

## Collection Format

Each dataset on Data.gov has a unique slug known as its `name`. We store each dataset in this repository as:

```
collections/data_gov/<name>/<version>.zip
```

We also store a metadata file for each dataset in the `metadata` directory:

```
metadata/data_gov/<name>/<version>.json
```

`<version>` is a `v` followed by the number of times we have downloaded the dataset
(v1, v2, etc.)

For example, the Data.gov dataset [https://catalog.data.gov/dataset/fruit-and-vegetable-prices](https://catalog.data.gov/dataset/fruit-and-vegetable-prices) is stored in this repository as:

- [collections/data_gov/fruit-and-vegetable-prices/v1.zip](https://source.coop/harvard-lil/gov-data/collections/data_gov/fruit-and-vegetable-prices)
- [metadata/data_gov/fruit-and-vegetable-prices/v1.json](https://source.coop/harvard-lil/gov-data/metadata/data_gov/fruit-and-vegetable-prices)

## Dataset Format

Each dataset zip file is a BagIt package created by our [bag-nabit](https://github.com/harvard-lil/bag-nabit) tool.

[BagIt](https://en.wikipedia.org/wiki/BagIt) is a simple file format, established by the Library of Congress, consisting of a folder of metadata and text files. Our BagIt files follow this directory structure:

- `data/`
  - `files/`:
    - `...`: these are the actual files you likely want to use as a researcher,
      downloaded from the Data.gov listing.
  - `headers.warc`: request and response headers from HTTP fetches for files in `files/`
  - `signed-metadata.json`: metadata including Data.gov's API description of the dataset

The bags also contain these files, which are useful for authenticating the provenance of the data:

- `bagit.txt`: standard BagIt file
- `bag-info.txt`: standard BagIt file
- `manifest-sha256.txt`: standard BagIt file
- `tagmanifest-sha256.txt`: standard BagIt file
- `signatures/`: directory of signature files

### Signatures

Every bag is signed with the Library Innovation Lab's GlobalSign certificate for `lil@law.harvard.edu` (SHA-256 fingerprint `FB:C8:FF:85:18:A9:C9:A4:CD:74:A2:D9:17:91:5D:1A:8A:45:9D:0F:CE:AF:47:C3:CC:14:F1:EE:F9:61:6E:24`), and the signature is timestamped by DigiCert. The certificate was obtained to sign this collection and was meant to lapse afterwards; it expired on 2025-12-06. The timestamp shows that each signature was made while the certificate was valid, so check signatures as of their timestamp rather than the current time. See [signing.md](https://github.com/harvard-lil/data-vault/blob/develop/docs/signing.md) for the certificate chain and verification steps.

## Metadata File Format

Each metadata JSON file contains three main attributes:

1. `bag_info`: Contains the BagIt metadata including:
   - Bag-Software-Agent: The version of nabit used to create the archive
   - Bagging-Date: When the archive was created

2. `signed_metadata`: Contains detailed information about the dataset including:
   - `id`: A UUID for this specific archive
   - `url`: The Data.gov URL for the dataset
   - `description`: A brief description including the dataset title and creating organization
   - `data_gov_metadata`: The complete metadata from Data.gov's API, including:
     - Dataset details (title, description, etc.)
     - Organization information
     - Resource listings
     - Tags and other metadata
   - `collection_tasks`: Records of the HTTP requests made to collect the dataset

3. `zip_entries`: Listing of each entry in the collection zip file, which can be used to fetch individual files from the zip file via range request without downloading the entire archive.

## Rollup files

There are several rollup files at the top level to help with finding datasets of interest:

- `metadata.csv.zip`: CSV listing the name, organization, title, date, metadata path, and collection path for each dataset
- `metadata.jsonl.zip`: JSON lines file with complete metadata for each dataset, including the `signed_metadata` and `zip_entries` sections (equivalent to downloading the metadata/ directory as a single file)
- `file_listing.jsonl.zip`: zipped JSON lines file showing the s3 listing of all files in the repository

## Downloading data

To download an individual dataset by name you can construct its URL, such as:

```
https://source.coop/harvard-lil/gov-data/collections/data_gov/fruit-and-vegetable-prices/v1.zip
https://source.coop/harvard-lil/gov-data/metadata/data_gov/fruit-and-vegetable-prices/v1.json
```

To download large numbers of files, we recommend the `aws` or `rclone` command line tools:

```
aws s3 cp s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/collections/data_gov/<name>/v1.zip --no-sign-request
```

## Data Limitations

Data.gov includes many kinds of datasets, including some that link to actual data files, such as CSV files, and some that link to separate websites. Our process runs a "shallow crawl" that collects only the directly linked files. Datasets that link only to a separate website will need to be collected separately.

## Errata

- **120 datasets are listed but cannot be downloaded.** Each has an entry in `metadata.jsonl.zip`, `metadata.csv.zip` and [Data.gov Archive Search](https://lil.law.harvard.edu/data-gov-archive/), but no file under `collections/` or `metadata/`. They were bagged between 2024-12-09 and 2024-12-16, but the bags never reached this repository, and no other copy has been found. The cause is not known. When checked in October 2026, 116 of them still had their source files online. [unavailable-datasets.csv](https://github.com/harvard-lil/data-vault/blob/develop/docs/unavailable-datasets.csv) lists all 120 with their organization, title, bagging date, bag size, and whether the Data.gov page and source files were still online.
- **96 datasets were listed but not downloadable until 2026-10-20.** Their bags failed to upload in 2024–2025 and were uploaded on 2026-10-20. Their signatures and timestamps date from when they were bagged.
- **3 datasets were missing their metadata file until 2026-10-20:** `african-easterly-wave-climatology-version-1`, `kdpar-and-surface-water-quality-data-collected-in-the-sacramento-san-joaquin-river-delta-i` and `teq-array-station-sfnp-bottom-temperature1`. Their zip files were already published.
- **The `collection_path` column in `metadata.csv.zip` ends in `/v1.json` on every row.** The zip file is at the same path with `/v1.zip`.
- **`file_listing.jsonl.zip` dates from 2025-02-06,** so it does not include files uploaded on 2026-10-20.
## Source code

The source code used to generate this and other repositories is available at [https://github.com/harvard-lil/data-vault](https://github.com/harvard-lil/data-vault).

We welcome conversation and collaboration in the issue tracker for that project.
