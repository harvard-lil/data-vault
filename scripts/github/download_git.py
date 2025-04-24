import csv
import logging
from pathlib import Path
from scripts.helpers.parallel import run_parallel
import click
from tqdm import tqdm
from gitspoke import Downloader, GitHubAPI
from gitspoke.cli import valid_include_items, get_token
import uuid
import requests
from datetime import datetime
from scripts.helpers.misc import load_config
from nabit.lib.backends.path import PathCollectionTask
from scripts.helpers.bag import fetch_and_upload, parse_signatures

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

def get_date_range(path):
    """Get the date range of a directory."""
    dates = []
    for file in path.glob('**/*'):
        if file.is_file():
            dates.append(datetime.fromtimestamp(file.stat().st_mtime))
    return min(dates), max(dates)

def run_pipeline(
    org_name, 
    repo_name, 
    collection_path, 
    metadata_path=None,
    include=None, 
    token=None,
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
        collect_dir = None

        # first see if we can get the data from raw_dir
        if raw_dir:
            raw_path = raw_dir / org_name / repo_name
            if raw_path.exists():
                collect_dir = raw_path

        # else download
        if not collect_dir:
            Downloader(org_name, repo_name, token, max_retries=20).download_repo(temp_dir, include=include)
            collect_dir = temp_dir

        start_date, end_date = get_date_range(collect_dir)
        return {
            'collect': [
                PathCollectionTask(path=collect_dir)
            ],
            'signed_metadata': {
                'id': str(uuid.uuid4()),
                'url': f'https://github.com/{org_name}/{repo_name}',
                'description': f'Archive of GitHub repository {org_name}/{repo_name}',
                'github_metadata': {
                    'org': org_name,
                    'repo': repo_name,
                    'download_start_date': start_date.isoformat(),
                    'download_end_date': end_date.isoformat(),
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
    skip_existing: bool = False,
    skip_rows: int = 0,
    stop_after: int | None = None,
    **kwargs,
):
    """Get repositories from CSV that haven't been processed yet."""
    # Initialize progress bars
    stats_counter['total'] = tqdm(desc="Total records", unit="repo")
    if skip_existing:
        stats_counter['skipped'] = tqdm(desc="Skipped", unit="repo")
        stats_counter['yielded'] = tqdm(desc="Processing", unit="repo")

    # handle --include
    if kwargs['include']:
        kwargs['include'] = kwargs['include'].split(',')
    else:
        kwargs['include'] = ['repo_info']
    
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

    output_path = kwargs['output_path']

    with open(csv_path, 'r') as file:
        reader = csv.DictReader(file)

        # Skip specified number of rows
        for _ in range(skip_rows):
            next(reader)
            
        processed = 0
        for row in reader:
            stats_counter['total'].update(1)
            
            if not row['html_url']:  # Skip empty rows
                continue
                
            org_name, repo_name = row['html_url'].split('/')[-2:]
            
            collection_path = output_path / 'data' / org_name / repo_name / 'v1.zip'
            metadata_path = output_path / 'metadata' / org_name / repo_name / 'v1.json'
                
            if skip_existing:
                if metadata_path.exists():
                    stats_counter['skipped'].update(1)
                    continue
                else:
                    stats_counter['yielded'].update(1)

            # use tokens round robin
            token = tokens[processed % len(tokens)]

            # Create kwargs dictionary for run_pipeline
            task_kwargs = {
                'org_name': org_name,
                'repo_name': repo_name,
                'metadata_path': metadata_path,
                'collection_path': collection_path,
                **kwargs,
            }

            yield task_kwargs

            processed += 1
            if stop_after and processed >= stop_after:
                break

    # Close progress bars
    for counter in stats_counter.values():
        counter.close()


@click.command()
@click.option('--output-path', '-o', type=click.Path(path_type=Path), default='data/federal_github',
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
@click.option('--raw-dir', type=click.Path(path_type=Path), help='Directory to save raw repositories to or fetch from')
# deletion checking
@click.option('--check-exists', is_flag=True, help='Only check if repositories still exist on GitHub')
@click.option('--output-deleted', type=click.Path(path_type=Path), help='File to output deleted repositories to')
def main(profile, workers, **kwargs):
    
    kwargs['session_args'] = {}
    if profile:
        kwargs['session_args']['profile_name'] = profile

    kwargs['signatures'] = parse_signatures(kwargs['signatures'])

    run_parallel(
        run_pipeline,
        get_tasks(**kwargs),
        workers,
    )

if __name__ == "__main__":
    main()