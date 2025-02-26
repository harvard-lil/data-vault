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
import uuid
import requests
from datetime import datetime
from scripts.helpers.misc import load_config
from nabit.lib.archive import package
from nabit.lib.sign import KNOWN_TSAS, is_encrypted_key
from nabit.lib.backends.path import PathCollectionTask
from scripts.helpers.bag import fetch_and_upload

logger = logging.getLogger(__name__)
stats_counter = {}

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

def run_pipeline(
    org_name, 
    repo_name, 
    collection_path, 
    include, 
    token,
    metadata_path=None,
    output_path=None,
    signatures=None,
    session_args=None,
    s3_path=None,
    no_delete=False,
    save_raw=False,
    raw_dir=None,
    check_exists=False,
    output_deleted=None,
):
    """Process a single repository."""
    # existing checking mode
    if check_exists:
        return check_repo_exists(org_name, repo_name, token, output_deleted)
    
    # raw saving mode
    if save_raw:
        raw_path = raw_dir / org_name / repo_name
        Downloader(org_name, repo_name, token, max_retries=20).download_repo(raw_path, include=include)
        logger.info("Processing complete")
        return
    
    def create_archive_callback(temp_dir):
        if raw_dir:
            raw_path = raw_dir / org_name / repo_name
            if raw_path.exists():
                out_dir = raw_path
        else:
            Downloader(org_name, repo_name, token, max_retries=20).download_repo(temp_dir, include=include)
            out_dir = temp_dir
        return {
            'collect': [
                PathCollectionTask(path=out_dir)
            ],
            'signed_metadata': {
                'id': str(uuid.uuid4()),
                'url': f'https://github.com/{org_name}/{repo_name}',
                'description': f'Archive of GitHub repository {org_name}/{repo_name}',
                'github_metadata': {
                    'org': org_name,
                    'repo': repo_name,
                    'archived_date': datetime.now().isoformat()
                },
            },
        }

    # Archive mode - use common pipeline
    fetch_and_upload(
        output_path=output_path,
        collection_path=collection_path,
        metadata_path=metadata_path,
        create_archive_callback=create_archive_callback,
        signatures=signatures,
        session_args=session_args,
        s3_path=s3_path,
        no_delete=no_delete
    )
    
    logger.info("Processing complete")

def get_tasks(
    csv_path: Path,
    output_path: Path,
    skip_rows: int = 0,
    skip_existing: bool = False, 
    stop_after: int = None,
    include: str = None,
    archive_mode: bool = False,
    signatures: list = None,
    session_args: dict = None,
    s3_path: str = None,
    no_delete: bool = False,
    save_raw: bool = False,
    raw_dir: Path = None,
    check_exists: bool = False,
    output_deleted: Path = None,
):
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
            
            collection_path = output_path / 'data' / org_name / repo_name / 'v1.zip'
            metadata_path = output_path / 'metadata' / org_name / repo_name / 'v1.json'
                
            if skip_existing and collection_path.exists():
                stats_counter['skipped'].update(1)
                continue
            else:
                stats_counter['yielded'].update(1)

            # use tokens round robin
            token = tokens[processed % len(tokens)]

            yield (
                org_name,
                repo_name,
                collection_path,
                include,
                token,
                output_deleted,
                archive_mode,
                metadata_path,
                output_path,
                signatures,
                session_args,
                s3_path,
                save_raw,
                raw_dir,
                check_exists,
                no_delete,
            )

            processed += 1
            if stop_after and processed >= stop_after:
                break

    # Close progress bars
    for counter in stats_counter.values():
        counter.close()


@click.command()
@click.option('--output-path', '-o', type=click.Path(path_type=Path), default='data/processed',
              help='Output path.')
@click.option('--workers', '-w', type=int, default=None, 
              help='Number of worker processes. Defaults to CPU count.')
@click.option('--skip-rows', type=int, default=0,
              help='Number of rows to skip in the CSV.')
@click.option('--include', 
              help='Comma-separated list of elements to include: ' + ', '.join(valid_include_items))
@click.option('--csv-path', '-csv', type=click.Path(path_type=Path), default='data/repos_by_cumulative_popularity.csv',
              help='Path to the CSV file.')
@click.option('--stop-after', help='Stop after processing this many repositories', type=int)
@click.option('--skip-existing', is_flag=True, help='Set to skip existing repositories')
@click.option('--signatures', help='JSON string of signature configuration.')
# upload settings
@click.option('--profile', '-p', help='AWS profile name')
@click.option('--s3-path', '-s', help='S3 path for uploads, e.g. "<bucket_name>/<path>"')
@click.option('--no-delete', is_flag=True, help='Set to preserve zipped data on disk as well as metadata')
# raw saving
# useful if doing multiple runs with the same csv and different --include values
@click.option('--save-raw', is_flag=True, help='Save raw repositories to disk rather than bagging and uploading')
@click.option('--raw-dir', type=click.Path(path_type=Path), help='Directory to save raw repositories to')
# deletion checking
@click.option('--check-exists', is_flag=True, help='Only check if repositories still exist on GitHub')
@click.option('--output-deleted', type=click.Path(path_type=Path), help='File to output deleted repositories to')
def main(profile, workers, **kwargs):
    
    session_args = {}
    if profile:
        session_args['profile_name'] = profile

    if signatures := kwargs.get('signatures'):
        signatures = json.loads(signatures)
        for signature in signatures:
            if signature['action'] == 'sign':
                if is_encrypted_key(signature['params']['key']):
                    signature['params']['password'] = click.prompt(
                        f"Enter password for {signature['params']['key']}: ", 
                        hide_input=True
                    )
            elif signature['action'] == 'timestamp':
                if known_tsa := signature.pop('known_tsa', None):
                    signature['params'] = KNOWN_TSAS[known_tsa]
        kwargs['signatures'] = signatures
    
    run_parallel(
        run_pipeline,
        get_tasks(**kwargs),
        workers,
    )

if __name__ == "__main__":
    main()