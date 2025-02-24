import httpx
import time
from typing import Any, Dict, Iterator
import logging

logger = logging.getLogger(__name__)

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