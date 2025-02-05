import json
import click
from pathlib import Path
from typing import Dict, List, Set, Tuple
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)


def load_jsonl_data(jsonl_path: Path, keep_fields=None, compare_by: str = 'id') -> Dict[str, dict]:
    """
    Load data from JSONL file into a dictionary keyed by id.
    Only includes fields that match the CSV format.
    
    Args:
        jsonl_path: Path to the JSONL file
        
    Returns:
        Dictionary mapping id to filtered record data
    """
    # Fields to keep from JSONL records
    
    data = {}
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in tqdm(f, desc="Loading JSONL"):
            if line.strip():  # Skip empty lines
                record = json.loads(line)
                if keep_fields:
                    record = {k: v for k, v in record.items() if k in keep_fields}
                data[record[compare_by]] = record
                
    return data

def find_differences(csv_data: Dict[str, dict], 
                    jsonl_data: Dict[str, dict]) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Find records that differ between CSV and JSONL data.
    
    Args:
        csv_data: Dictionary of CSV records keyed by id
        jsonl_data: Dictionary of JSONL records keyed by id
        
    Returns:
        Tuple of (csv_only_ids, jsonl_only_ids, different_ids)
    """
    csv_ids = set(csv_data.keys())
    jsonl_ids = set(jsonl_data.keys())
    
    # Find records only in CSV
    csv_only = csv_ids - jsonl_ids
    
    # Find records only in JSONL
    jsonl_only = jsonl_ids - csv_ids
    
    return csv_only, jsonl_only

@click.command()
@click.argument('old_path', type=click.Path(exists=True, path_type=Path))
@click.argument('new_path', type=click.Path(exists=True, path_type=Path))
@click.option('--compare-by', '-c',
              default='id',
              help='Field to compare by.')
@click.option('--log-level', '-l',
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
              default='INFO',
              help='Logging level.')
def main(old_path: Path, new_path: Path, compare_by: str, log_level: str):
    """Compare records between CSV and JSONL files."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    old_data = load_jsonl_data(old_path, compare_by=compare_by)
    new_data = load_jsonl_data(new_path, compare_by=compare_by)
    
    # Find differences
    old_only, new_only = find_differences(old_data, new_data)

    old_only_path = old_path.with_suffix(f'.only_{compare_by}.jsonl')
    new_only_path = new_path.with_suffix(f'.only_{compare_by}.jsonl')

    logger.info(f"Writing {len(old_only)} records to {old_only_path}")
    with open(old_only_path, 'w', encoding='utf-8') as f:
        for id in old_only:
            f.write(json.dumps(old_data[id]) + '\n')

    logger.info(f"Writing {len(new_only)} records to {new_only_path}")
    with open(new_only_path, 'w', encoding='utf-8') as f:
        for id in new_only:
            f.write(json.dumps(new_data[id]) + '\n')

if __name__ == '__main__':
    main() 



# import sqlite3
# import json

# # Connect to the database
# conn = sqlite3.connect('data/data.db')
# conn.row_factory = sqlite3.Row  # This allows us to access columns by name

# # Open the output file
# with open('data/data_db_dump_20250130.jsonl', 'w') as f:
#     # Execute the query and fetch rows in chunks
#     cursor = conn.execute('''
#         SELECT *
#         FROM dataset
#     ''')
    
#     written = 0
#     while True:
#         rows = cursor.fetchmany(1000)  # Fetch 1000 rows at a time
#         if not rows:
#             break
#         written += len(rows)
#         # Write each row as a JSON line
#         for row in rows:
#             # Convert row to dict and write to file
#             json_line = json.dumps(dict(row))
#             f.write(json_line + '\n')
#         print(f"Wrote {written} rows")

# conn.close()