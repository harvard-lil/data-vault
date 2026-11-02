# Data.gov archive workflow

How the [harvard-lil/gov-data](https://source.coop/harvard-lil/gov-data)
collection on Source Cooperative was built, between 2024-11-19 and 2025-02-06.
The commands come from the shell history of the machine that ran the
collection (`lil-vector`, working directory `/collab/govdata/`). Collection
stopped on 2025-02-06 and the collection is not being updated.

## 1. Fetch the Data.gov catalog

```bash
uv run scripts/data_gov/fetch_index.py fetch
# resume from a given modification time
uv run scripts/data_gov/fetch_index.py fetch -s '2025-01-27T02:56:55Z'
```

This pages through Data.gov's CKAN API, 1,000 records per page by default
(`--rows-per-page`). It stores the current record for each dataset in the
`Dataset` table of `data/data.db`, and earlier versions of changed records in
`DatasetHistory`.

## 2. Fetch, bag, sign and upload each dataset

```bash
uv run scripts/data_gov/fetch_data.py \
  --signatures '[{"action": "sign", "params": {"key": "/home/jcushman/certs/globalsign.key", "cert_chain": "/home/jcushman/certs/globalsign.pem"}}, {"action": "timestamp", "known_tsa": "digicert"}]' \
  --s3-path us-west-2.opendata.source.coop/harvard-lil/gov-data \
  --profile sc-direct
```

For each dataset in `data/data.db` that has no local metadata file yet,
`fetch_data.py`:

1. Collects every URL found in the dataset's Data.gov metadata. This is a
   shallow crawl: datasets that only link to a landing page or separate
   website get that page, not the data behind it.
2. Packages the files with [bag-nabit](https://github.com/harvard-lil/bag-nabit)
   as a BagIt bag. The bag holds the downloaded files in `data/files/`, the
   HTTP headers in `data/headers.warc`, and the Data.gov record in
   `data/signed-metadata.json`.
3. Signs the bag's tag manifest with LIL's GlobalSign certificate and
   timestamps the signature with DigiCert. See [signing.md](signing.md).
4. Zips the bag and uploads `collections/data_gov/<name>/v1.zip` and
   `metadata/data_gov/<name>/v1.json` to the `--s3-path` with the `--profile`
   AWS credentials. It also writes the metadata JSON to
   `data/processed/metadata/`.

Other options:

- `--workers` / `-w`: number of parallel workers. The default is the CPU count.
- `--dataset-name`: process one dataset.
- `--min-size`: process only datasets of at least this size.
- `--no-delete`: keep the zipped bag on disk after upload.
- `--if-exists skip|replace|version` has no effect as written:
  `get_unprocessed_datasets` drops every dataset that already has a metadata
  file before `--if-exists` is checked.

`--min-size` and `--s3-path` both declare the short flag `-s`, so use the
long names.

### Known problems

These explain why some bags listed in the metadata rollups were missing from
Source Coop until October 2026:

- Downloads that fail are left out of the bag (`collect_errors='ignore'`),
  not retried.
- The local metadata JSON is written before the upload starts. On
  later runs, any dataset with a local metadata file is skipped, so a failed
  upload is never retried.
- With more than one worker, `scripts/helpers/parallel.py` logs exceptions
  and moves on, so failures show up only in the log.
- Some runs on 2025-02-06 passed `--s3-path harvard-lil/gov-data` with the
  `sc-direct` profile, which needs the full bucket path. Those bags stayed
  local until they were uploaded on 2026-10-20.

What these problems left in the published collection is listed in the
[Errata](../collections/data_gov/README.md#errata) section of the collection README.

## 3. Build the rollup files

```bash
uv run scripts/collection/write_metadata.py write-jsonl data/processed/metadata data/processed/metadata.jsonl.zip
uv run scripts/collection/write_metadata.py write-csv data/processed/metadata.jsonl.zip data/processed/metadata.csv.zip
aws --profile sc-direct s3 cp data/processed/metadata.jsonl.zip s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/
aws --profile sc-direct s3 cp data/processed/metadata.csv.zip s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/
```

The rollups are built from the local metadata directory, so they list every
dataset that was processed, including any whose upload failed.

## Published layout

```
collections/data_gov/<name>/v1.zip   BagIt bag
metadata/data_gov/<name>/v1.json     bag_info, signed_metadata, zip_entries
metadata.jsonl.zip                   all metadata files as JSON lines
metadata.csv.zip                     name, organization, title, date, paths
file_listing.jsonl.zip               S3 listing of the repository (2025-02-06)
```

`<name>` is the dataset's Data.gov `name`. Versions count downloads of a
dataset (`v1`, `v2`, …); only `v1` was published. The public README for the
collection is [`collections/data_gov/README.md`](../collections/data_gov/README.md).
