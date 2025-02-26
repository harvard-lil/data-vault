import json
import logging
import gzip
import pickle
from pathlib import Path
import click
from scripts.data_gov.helpers import fetch_data_gov_packages
from datetime import datetime
from typing import Dict, Any
from tqdm import tqdm
import deepdiff
import orjson

logger = logging.getLogger(__name__)

@click.group()
def cli():
    """Data.gov package management commands."""
    pass

@cli.command()
@click.argument('output_path', type=click.Path(path_type=Path))
@click.option('--rows-per-page', '-r', type=int, default=1000,
              help='Number of results to fetch per page.')
@click.option('--start-date', '-s', type=str, default=None,
              help='Start date for fetching packages in YYYY-MM-DD format.')
def fetch(output_path: Path, rows_per_page: int, log_level: str, start_date: str):
    """Fetch all package data from data.gov API and save to gzipped JSONL file."""
    if output_path.is_dir():
        current_date = datetime.now().strftime('%Y%m%d')
        output_path = output_path / f'data_{current_date}.jsonl.gz'

    logger.info(f"Writing to {output_path}")
    
    with gzip.open(output_path, 'at') as f:
        for results in fetch_data_gov_packages(rows_per_page=rows_per_page, start_date=start_date):
            for package in results:
                f.write(json.dumps(package) + '\n')

@cli.command()
@click.argument('file1', type=click.Path(exists=True, path_type=Path))
@click.argument('file2', type=click.Path(exists=True, path_type=Path))
def compare(file1: Path, file2: Path, log_level: str):
    """Compare two gzipped JSONL files by indexing on the 'name' key."""
    def load_jsonl_index(file_path: Path) -> Dict[str, Any]:
        # Check for pickle file
        pickle_path = file_path.with_suffix('.pickle')
        if pickle_path.exists():
            logger.info(f"Loading cached index from {pickle_path}")
            with open(pickle_path, 'rb') as f:
                return pickle.load(f)

        # If no pickle file exists, load from JSONL and create pickle
        index = {}
        with gzip.open(file_path, 'rt') as f:
            for line in tqdm(f, desc=f"Loading {file_path}"):
                record = orjson.loads(line)
                index[record['name']] = record

        # Save to pickle for future runs
        logger.info(f"Saving index to {pickle_path}")
        with open(pickle_path, 'wb') as f:
            pickle.dump(index, f)

        return index

    logger.info(f"Loading {file1}")
    index1 = load_jsonl_index(file1)
    logger.info(f"Loading {file2}")
    index2 = load_jsonl_index(file2)

    names1 = set(index1.keys())
    names2 = set(index2.keys())

    only_in_file1 = [index1[name] for name in names1 - names2]
    only_in_file2 = [index2[name] for name in names2 - names1]
    names_in_both = names1 & names2
    changed = [[index1[name], index2[name]] for name in tqdm(names_in_both, desc="Changed") if index1[name] != index2[name]]
    changed_deep = [[diff.to_json(), item1, item2] for item1, item2 in tqdm(changed[:1000], desc="Changed (deep)") if (diff := deepdiff.DeepDiff(item1, item2, ignore_order=True))]
    
    # for suffix, items in [
    #     ('added', only_in_file2),
    #     ('removed', only_in_file1),
    #     ('changed', changed),
    #     ('changed_deep', changed_deep)
    # ]:
    #     logger.info(f"Writing {suffix}: {len(items)}")
    #     output_path = file2.parent / f'{file2.stem}_{suffix}.jsonl.gz'
    #     with gzip.open(output_path, 'wt') as f:
    #         for item in tqdm(items, desc=suffix):
    #             f.write(json.dumps(item) + '\n')

    breakpoint()

if __name__ == "__main__":
    cli()
