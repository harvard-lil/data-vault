<img src="https://data.source.coop/harvard-lil/gov-data/docs/LIL_HLSL_logos.png" alt="Harvard Law School Library Innovation Lab logo"/>

This is a regularly updated mirror of all data files linked from [data.gov](https://data.gov).

The repository is maintained by the Harvard Law School Library Innovation Lab as part
of our [project to preserve U.S. federal public data](https://lil.law.harvard.edu/blog/2025/01/30/preserving-public-u-s-federal-data/).

Collection Format
-----------------

Each dataset on data.gov has a unique slug known as its `name`. We store each dataset
in this repository as:

```
collections/data_gov/<name>/<version>.zip
```

We also store a metadata file for each dataset in the `metadata` directory:

```
metadata/data_gov/<name>/<version>.json
```

`<version>` is a `v` followed by the number of times we have downloaded the dataset
(v1, v2, etc.)

For example, the data.gov dataset [https://catalog.data.gov/dataset/fruit-and-vegetable-prices](https://catalog.data.gov/dataset/fruit-and-vegetable-prices)
is stored in this repository as:

* [collections/data_gov/fruit-and-vegetable-prices/v1.zip](https://source.coop/harvard-lil/gov-data/collections/data_gov/fruit-and-vegetable-prices)
* [metadata/data_gov/fruit-and-vegetable-prices/v1.json](https://source.coop/harvard-lil/gov-data/metadata/data_gov/fruit-and-vegetable-prices)


Dataset Format
--------------

Each dataset zip file is a BagIt package created by our [bag-nabit](https://github.com/harvard-lil/bag-nabit) tool.

[BagIt](https://en.wikipedia.org/wiki/BagIt) is a simple file format, established by the
Library of Congress, consisting of a folder of metadata and text files. Our BagIt
files follow this directory structure:

* `data/`
  * `files/`: 
    * `...`: these are the actual files you likely want to use as a researcher,
             downloaded from the data.gov listing.
  * `headers.warc`: request and response headers from HTTP fetches for files in `files/`
  * `signed-metadata.json`: metadata including data.gov's API description of the dataset

The bags also contain these files, which are useful for authenticating the
provenance of the data:

* `bagit.txt`: standard BagIt file
* `bag-info.txt`: standard BagIt file  
* `manifest-sha256.txt`: standard BagIt file
* `tagmanifest-sha256.txt`: standard BagIt file
* `signatures/`: directory of signature files

Metadata File Format
--------------------

Each metadata JSON file contains three main sections:

1. `bag_info`: Contains the BagIt metadata including:
   - Bag-Software-Agent: The version of nabit used to create the archive
   - Bagging-Date: When the archive was created

2. `signed_metadata`: Contains detailed information about the dataset including:
   - `id`: A UUID for this specific archive
   - `url`: The data.gov URL for the dataset
   - `description`: A brief description including the dataset title and creating organization
   - `data_gov_metadata`: The complete metadata from data.gov's API, including:
     - Dataset details (title, description, etc.)
     - Organization information
     - Resource listings
     - Tags and other metadata
   - `collection_tasks`: Records of the HTTP requests made to collect the dataset

3. `zip_entries`: Listing of each entry in the collection zip file, which can be used to fetch individual files from the zip file via range request without downloading the entire archive.

Rollup files
------------

There are several rollup files at the top level to help with finding datasets
of interest:

* `metadata.jsonl.zip`: zipped JSON lines file of all files contained in metadata/
* `file_listing.jsonl.zip`: zipped JSON lines file showing the s3 listing of all files in the repository
* `collections.html`: human-readable HTML file showing the title and link to each dataset (warning, very large file that may not load in some browsers)

Downloading data
----------------

To download an individual dataset by name you can construct its URL, such as:

```
https://source.coop/harvard-lil/gov-data/collections/data_gov/fruit-and-vegetable-prices/v1.zip
https://source.coop/harvard-lil/gov-data/metadata/data_gov/fruit-and-vegetable-prices/v1.json
```

To download large numbers of files, we recommend the `aws` or `rclone` command line tools:

```
aws s3 cp s3://us-west-2.opendata.source.coop/harvard-lil/gov-data/collections/data_gov/<name>/v1.zip --no-sign-request
```

Data Limitations
----------------

data.gov includes multiple kinds of datasets, including some that link to actual data
files, such as CSV files, and some that link to HTML landing pages. Our process
runs a "shallow crawl" that collects only the directly linked files. Datasets
that link only to a landing page will need to be collected separately.

Source code
-----------

The source code used to generate this and other repositories is available at [https://github.com/harvard-lil/data-vault](https://github.com/harvard-lil/data-vault).
We welcome conversation and collaboration in the issue tracker for that project.
