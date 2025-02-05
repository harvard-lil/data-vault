import httpx
import json
import time
import logging
from pathlib import Path
from typing import Iterator, Dict, Any, List
import click
from scripts.data_gov.fetch_index import fetch_data_gov_packages

logger = logging.getLogger(__name__)

@click.command()
@click.argument('output_path', type=click.Path(path_type=Path), default='data/data_20250130.jsonl')
@click.option('--rows-per-page', '-r', type=int, default=1000,
              help='Number of results to fetch per page.')
@click.option('--log-level', '-l', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO',
              help='Logging level.')
@click.option('--start-date', '-s', type=str, default=None,
              help='Start date for fetching packages in YYYY-MM-DD format.')
def main(output_path: Path, rows_per_page: int, log_level: str, start_date: str):
    """Fetch all package data from data.gov API and save to JSONL file."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    with open(output_path, 'a') as f:
        for results in fetch_data_gov_packages(rows_per_page=rows_per_page, start_date=start_date):
            for package in results:
                f.write(json.dumps(package) + '\n')

if __name__ == "__main__":
    main()
