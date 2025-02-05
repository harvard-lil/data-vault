import httpx
from typing import Iterator, Dict, Any, List
import time
import click
from pathlib import Path
import logging
from datetime import datetime
from scripts.data_gov.models import db, Dataset, DatasetHistory
from tqdm import tqdm
from playhouse.shortcuts import model_to_dict
from jsondiff import diff

logger = logging.getLogger(__name__)

stats_counter = {}

def init_database(db_path: Path) -> None:
    """Initialize the database connection and create tables."""
    db.init(db_path)
    db.connect()
    db.create_tables([Dataset, DatasetHistory])

def save_to_database(results: List[Dict[str, Any]]) -> None:
    """
    Save a batch of packages to the database using Peewee.
    """
    if not results:
        return

    # Process datetime fields in incoming records
    for package in results:
        for field in ['metadata_created', 'metadata_modified']:
            if package.get(field):
                try:
                    package[field] = datetime.fromisoformat(
                        package[field].replace('Z', '+00:00')
                    )
                except ValueError:
                    package[field] = None

    # Get all IDs from incoming packages
    incoming_ids = [pkg['id'] for pkg in results]
    
    # Fetch existing records as model instances
    existing_records = {
        record.id: record
        for record in Dataset.select().where(Dataset.id << incoming_ids)
    }

    # Prepare bulk operations
    history_records = []
    new_records = []

    # Compare records and prepare operations
    for package_data in results:
        # Create a new model instance from the package data
        new_package = Dataset(**package_data)
        existing = existing_records.get(package_data['id'])
        
        if existing:
            # Compare model instances using their dict representations
            if diff(model_to_dict(existing), model_to_dict(new_package)):
                # Record changed - add to history and update
                history_records.append(existing)
                new_records.append(new_package)
                stats_counter['updated'].update(1)
            else:
                # Record unchanged - skip
                stats_counter['skipped'].update(1)
                continue
        else:
            # New record - just add it
            new_records.append(new_package)
            stats_counter['new'].update(1)

    with db.atomic():
        # Bulk move history records if any exist
        if history_records:
            DatasetHistory.bulk_create(history_records)
            Dataset.delete().where(Dataset.id << [h.id for h in history_records]).execute()
            
        # Bulk insert new records
        if new_records:
            Dataset.bulk_create(new_records)

def save_packages_to_database(output_path: Path, rows_per_page: int = 1000, start_date: str | None = None) -> None:
    """
    Save fetched data to the database, resuming from last position if needed.
    
    Args:
        output_path: Path to save the database
        rows_per_page: Number of results to fetch per page
        start_date: Optional date to start fetching from
    """
    stats_counter['new'] = tqdm(desc="New records", unit="pkg")
    stats_counter['updated'] = tqdm(desc="Updated records", unit="pkg")
    stats_counter['skipped'] = tqdm(desc="Unchanged records", unit="pkg")

    init_database(output_path)
    
    try:
        for results in tqdm(fetch_data_gov_packages(rows_per_page=rows_per_page, start_date=start_date, max_retries=10)):
            save_to_database(results)
    finally:
        db.close()

def fetch_data_gov_packages(rows_per_page: int = 1000, start_date: str = None, max_retries: int = 3) -> Iterator[Dict[str, Any]]:
    """
    Fetch package data from data.gov API using date-based pagination.
    
    Args:
        rows_per_page: Number of results to fetch per page
        start_date: Optional date to start fetching from (format: YYYY-MM-DDTHH:MM:SS.mmmmmm)
        max_retries: Maximum number of retry attempts for 5xx errors
    
    Yields:
        Dict containing package data for each result
    """
    
    base_url = "https://catalog.data.gov/api/3/action/package_search"
    current_date = start_date
    total_records = 0
    
    while True:
        logger.info(f"Current date offset: {current_date}")

        # Build date filter query
        url = f"{base_url}?rows={rows_per_page}&sort=metadata_modified+desc"
        if current_date:
            # Format date to match Solr's expected format (dropping microseconds)
            formatted_date = current_date.split('.')[0] + 'Z'
            date_filter = f"+metadata_modified:[* TO {formatted_date}]"
            url += f"&fq={date_filter}"
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                response = httpx.get(url, timeout=60.0)
                request_time = time.time() - start_time
                
                response.raise_for_status()
                break  # Success, exit retry loop
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    retry_wait = 2 ** attempt  # Exponential backoff
                    logger.warning(f"Got {e.response.status_code}, retrying in {retry_wait}s... (attempt {attempt + 1}/{max_retries})")
                    logger.warning(f"Error URL: {url}")
                    time.sleep(retry_wait)
                    continue
                # If not a 5xx error or we're out of retries, re-raise
                logger.error(f"Error URL: {url}")
                logger.error(f"Response content: {response.text}")
                raise
        
        data = response.json()
        results = data["result"]["results"]
        
        if not results:
            break
            
        # Get date of last result for next query
        current_date = results[-1]["metadata_modified"]

        total_records += len(results)
        logger.info(f"Request took {request_time:.2f}s. Total records: {total_records}")
            
        yield results
        
        time.sleep(1)

def get_dataset_history(dataset_name: str) -> None:
    """
    Fetch and display all versions of a dataset with the given ID,
    from oldest to newest, showing only changed fields between versions.
    """
    # Get all versions including current
    versions = [
        model_to_dict(record, recurse=True)
        for record in (DatasetHistory
                      .select()
                      .where(DatasetHistory.name == dataset_name)
                      .order_by(DatasetHistory.metadata_modified))
    ]
    current_record = Dataset.select().where(Dataset.name == dataset_name).first()
    if current_record:
        versions.append(model_to_dict(current_record, recurse=True))

    if not versions:
        print(f"No dataset found with name: {dataset_name}")
        return
    
    # Print each version with changed fields
    prev = None
    for curr in versions:
        history_id = curr.pop('history_id', None)
        if prev:
            diff_fields = diff(prev, curr)
        else:
            diff_fields = curr

        print(f"*** Version: {curr.get('metadata_modified')} ***")
        for k, v in diff_fields.items():
            print(f"- {k}: {v}")
        print("\n")
        prev = curr

@click.group()
def cli():
    """Data.gov dataset mirroring tools."""
    pass

# Modify the existing main function to be a command in the group
@cli.command()
@click.argument('output_path', type=click.Path(path_type=Path), default='data/data.db')
@click.option('--rows-per-page', '-r', type=int, default=1000,
              help='Number of results to fetch per page.')
@click.option('--start-date', '-s', type=str, default=None,
              help='Date to start fetching from (format: YYYY-MM-DDTHH:MM:SS.mmmmmm)')
@click.option('--log-level', '-l', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='WARNING',
              help='Logging level.')
def fetch(output_path: Path, rows_per_page: int, start_date: str, log_level: str):
    """Fetch package data from data.gov API and save to database."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    save_packages_to_database(output_path, rows_per_page, start_date)

@cli.command()
@click.argument('dataset_name')
@click.argument('db_path', type=click.Path(path_type=Path), default='data/data.db')
def history(dataset_name: str, db_path: Path):
    """Show version history for a dataset with the given ID."""
    init_database(db_path)
    try:
        get_dataset_history(dataset_name)
    finally:
        db.close()

@cli.command()
@click.argument('db_path', type=click.Path(path_type=Path), default='data/data.db')
def delete_duplicate_history(db_path: Path):
    """Delete duplicate history records."""
    init_database(db_path)
    try:
        # Get all unique dataset names in history
        unique_names = (DatasetHistory
                       .select(DatasetHistory.name)
                       .distinct()
                       .tuples())

        total_deleted = 0
        for (name,) in tqdm(unique_names, desc="Processing datasets"):
            # Get all versions for this dataset ordered by modification date
            versions = [
                model_to_dict(record)
                for record in (DatasetHistory
                             .select()
                             .where(DatasetHistory.name == name)
                             .order_by(DatasetHistory.metadata_modified))
            ]
            current_record = Dataset.select().where(Dataset.name == name).first()
            if current_record:
                versions.append(model_to_dict(current_record))

            # Track IDs of duplicate records to delete
            to_delete = []
            
            # Compare adjacent versions
            prev = versions[0]
            prev_id = prev.pop('history_id')
            for curr in versions[1:]:
                curr_id = curr.pop('history_id', None)
                
                # If versions are identical, mark current version for deletion
                if not diff(prev, curr):
                    to_delete.append(prev_id)
                prev = curr
                prev_id = curr_id

            # Bulk delete duplicate records
            if to_delete:
                deleted = (DatasetHistory
                          .delete()
                          .where(DatasetHistory.history_id << to_delete)
                          .execute())
                total_deleted += deleted

        click.echo(f"Deleted {total_deleted} duplicate history records")
    finally:
        db.close()

if __name__ == "__main__":
    cli()

