This repository collects scripts to support the Library Innovation Lab's
[public data preservation project](https://lil.law.harvard.edu/blog/2025/01/30/preserving-public-u-s-federal-data/).

These scripts are used as part of internal pipelines, so may not be usable
for others as is, but are available for reference about the creation of our
data and for remix. We also welcome contributions if they fit our internal
pipelines and goals.

## Scripts

Scripts are organized into subfolders for general categories of tasks:

### collection

Scripts for working with a "collection," meaning a set of files stored on
cloud storage that were all gathered with a similar collection strategy.
This folder is for scripts that apply to multiple collections rather than
a single collection.

* sync.py: copy static files from collections/ to configure the collections.
* render.py: generate static indexes of files in a collection.
* verify_upload.py: fetch and verify integrity of a BagIt archive in a collection.
* cloudflare_tools.py: manage Cloudflare R2 buckets.
* s3_tools.py: manage S3 buckets.

### helpers

Util libraries used by other scripts.

* parallel.py: run tasks in parallel.
* config.py: load configuration from the user's home dir.

### data_gov

Scripts for working with the [data.gov collection](https://source.coop/repositories/harvard-lil/gov-data/description) .

* fetch_jsonl.py: fetch a jsonl file of the full API.
* fetch_index.py: fetch the full API and store updates in a sqlite database.
* models.py: database models for the sqlite database.
* fetch_data.py: use the sqlite database to fetch any datasets that require updating,
  package with nabit, and upload to cloud storage.
* models.py: database models for the sqlite database.
* data_gov_diff/: scripts for identifying changes in past data created by fetch_jsonl.py or fetch_index.py (WIP).

### GitHub

Scripts for working with the GitHub collection.

* download_git.py: use [gitspoke](https://github.com/harvard-lil/gitspoke) to download all repositories listed in a CSV.

