import csv
import logging
from pathlib import Path
from scripts.helpers.parallel import run_parallel
import click
from tqdm import tqdm
from gitspoke import Downloader, GitHubAPI
from gitspoke.cli import valid_include_items, get_token
import os
import json
import requests
from scripts.helpers.config import load_config

logger = logging.getLogger(__name__)
stats_counter = {}

CONFIG_PATH = (os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "data-mirror" / "config.json"

def check_repo_exists(org_name, repo_name, token, output_path=None):
    """Check if a repository still exists on GitHub."""
    exists = True
    try:
        GitHubAPI(token).request(f"repos/{org_name}/{repo_name}", method="HEAD")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            exists = False
        else:
            raise e
    if not exists:
        repo_link = f"https://github.com/{org_name}/{repo_name}"
        print(repo_link)
        if output_path:
            with open(output_path, 'a') as output_file:
                output_file.write(f"{repo_link}\n")
    return exists

def run_pipeline(org_name, repo_name, collection_path, include, token, check_exists=False, output_path=None):
    """Process a single repository."""
    if check_exists:
        return check_repo_exists(org_name, repo_name, token, output_path)
        
    logger.info(f"Processing repository: {org_name}/{repo_name}")
    Downloader(org_name, repo_name, token, max_retries=20).download_repo(collection_path, include=include)
    logger.info("Processing complete")

def get_tasks(csv_path: Path, output_path: Path, collection: str, skip_rows: int = 0, skip_existing: bool = False, stop_after: int = None, include: str = None,
              check_exists: bool = False):
    """Get repositories from CSV that haven't been processed yet."""
    # Initialize progress bars
    if not check_exists:
        stats_counter['total'] = tqdm(desc="Total records", unit="repo")
        if skip_existing:
            stats_counter['skipped'] = tqdm(desc="Skipped", unit="repo")
            stats_counter['yielded'] = tqdm(desc="Processing", unit="repo")

    # handle --include
    if include:
        include = include.split(',')
    else:
        include = ['repo_info']
    
    # import token or tokens
    config = load_config()
    if config.get('tokens'):
        tokens = config['tokens']
    else:
        tokens = [get_token(None)]
    if tokens != [None]:
        logger.warning(f"Using {len(tokens)} tokens")
    else:
        logger.warning("Using unauthenticated rate limits")

    with open(csv_path, 'r') as file:
        reader = csv.DictReader(file)
        # Skip specified number of rows
        for _ in range(skip_rows):
            next(reader)
            
        processed = 0
        for row in reader:
            if not check_exists:
                stats_counter['total'].update(1)
            
            if not row['html_url']:  # Skip empty rows
                continue
                
            org_name, repo_name = row['html_url'].split('/')[-2:]
            collection_path = output_path / 'collections' / collection / org_name / repo_name
            
            if skip_existing:
                if collection_path.exists():
                    stats_counter['skipped'].update(1)
                    continue
                else:
                    stats_counter['yielded'].update(1)

            # use tokens round robin
            token = tokens[processed % len(tokens)]

            yield org_name, repo_name, collection_path, include, token, check_exists, output_path

            processed += 1
            if stop_after and processed >= stop_after:
                break

    # Close progress bars
    for counter in stats_counter.values():
        counter.close()

@click.command()
@click.option('--output-path', '-o', type=click.Path(path_type=Path), default='data/processed',
              help='Output path.')
@click.option('--collection', '-c', type=str, default='github_raw',
              help='Collection name.')
@click.option('--workers', '-w', type=int, default=None, 
              help='Number of worker processes. Defaults to CPU count.')
@click.option('--skip-rows', type=int, default=0,
              help='Number of rows to skip in the CSV.')
@click.option('--include', 
              help='Comma-separated list of elements to include: ' + ', '.join(valid_include_items))
@click.option('--csv-path', '-csv', type=click.Path(path_type=Path), default='data/repos_by_cumulative_popularity.csv',
              help='Path to the CSV file.')
@click.option('--log-level', '-l', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default=None,
              help='Logging level.')
@click.option('--stop-after', help='Stop after processing this many repositories', type=int)
@click.option('--skip-existing', is_flag=True, help='Set to skip existing repositories')
@click.option('--check-exists', is_flag=True, help='Only check if repositories still exist on GitHub')
def main(csv_path: Path, output_path: Path, collection: str, workers=None, skip_rows=0, include=None,
         log_level=None, stop_after=None, skip_existing=False, check_exists=False):
    
    run_parallel(
        run_pipeline,
        get_tasks(csv_path, output_path, collection, skip_rows, skip_existing, stop_after, include, check_exists),
        workers,
        log_level=log_level
    )

if __name__ == "__main__":
    main()