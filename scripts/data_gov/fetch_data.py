from nabit.lib.archive import package
from nabit.lib.sign import KNOWN_TSAS, is_encrypted_key
from nabit.lib.backends.url import UrlCollectionTask
from pathlib import Path
import json
import uuid
import tempfile
import click
import os
from urllib.parse import urlparse
import re
from scripts.helpers.parallel import run_parallel
import zipfile
import struct
import boto3
import logging
from scripts.data_gov.models import db, Dataset
from playhouse.shortcuts import model_to_dict
from tqdm import tqdm
from datetime import datetime

logger = logging.getLogger(__name__)

## download data.gov datasets, create nabit archives, and upload to S3

# File extensions that are already compressed or wouldn't benefit from additional compression
UNCOMPRESSED_EXTENSIONS = {
    # Already compressed archives
    'zip', 'gz', 'tgz', 'bz2', '7z', 'rar', 'xz',
    # Compressed images
    'jpg', 'jpeg', 'png', 'gif', 'webp',
    # Compressed video/audio
    'mp4', 'mov', 'avi', 'wmv', 'ogv', 'mp3', 'm4a',
    # Other compressed/binary formats
    'pdf', 'docx', 'xlsx', 'pptx',
}

stats_counter = {}

def is_valid_url(url):
    parsed = urlparse(url)
    return parsed.scheme in ['http', 'https'] and re.search(r'[^\.]\.[^\.]', parsed.netloc)

def extract_urls(data, urls = None):
    urls = set() if urls is None else urls
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                if is_valid_url(value):
                    urls.add(value)
            elif isinstance(value, (dict, list)):
                extract_urls(value, urls)
    elif isinstance(data, list):
        for item in data:
            extract_urls(item, urls)
    return urls

def create_archive(bag_dir, dataset: Dataset, signatures):
    data_dict = model_to_dict(dataset)
    for key, value in data_dict.items():
        if isinstance(value, datetime):
            data_dict[key] = value.isoformat()
    data_gov_url = f'https://catalog.data.gov/dataset/{dataset.name}'
    collect = [
        *[UrlCollectionTask(url=url) for url in extract_urls(data_dict)],
    ]
    logger.info(f"  - Downloading {len(collect)} files")

    # sort fields from dataset
    data_gov_metadata = {k: v for k, v in data_dict.items() if not k.startswith('crawler_')}
    crawler_metadata = {k: v for k, v in data_dict.items() if k.startswith('crawler_')}

    # Create the archive
    package(
        output_path=bag_dir,
        collect=collect,
        collect_errors='ignore',
        signed_metadata={
            'id': str(uuid.uuid4()),
            'url': data_gov_url,
            'description': f'Archive of data.gov dataset "{dataset.title}" created by {dataset.organization["title"]}. Full metadata stored in data_gov_metadata key.',
            'data_gov_metadata': data_gov_metadata,
            'crawler_metadata': crawler_metadata,
        },
        signatures=signatures,
    )

def zip_archive(bag_dir, archive_path):
    # Create zip archive
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in bag_dir.rglob('*'):
            if file_path.is_file():
                arc_path = file_path.relative_to(bag_dir)
                compression = (zipfile.ZIP_STORED 
                            if file_path.suffix.lower().lstrip('.') in UNCOMPRESSED_EXTENSIONS 
                            else zipfile.ZIP_DEFLATED)
                zf.write(file_path, arc_path, compress_type=compression)

    # Create metadata file
    zip_info = []
    with zipfile.ZipFile(archive_path, 'r') as zf:
        for info in zf.filelist:
            header_offset = info.header_offset
            
            # Read header to calculate data offset
            zf.fp.seek(header_offset)
            header = zf.fp.read(zipfile.sizeFileHeader)
            fheader = struct.unpack(zipfile.structFileHeader, header)
            fname_length = fheader[zipfile._FH_FILENAME_LENGTH]
            extra_length = fheader[zipfile._FH_EXTRA_FIELD_LENGTH]
            data_offset = header_offset + zipfile.sizeFileHeader + fname_length + extra_length
            
            zip_info.append({
                'filename': info.filename,
                'file_size': info.file_size,
                'compress_size': info.compress_size,
                'compress_type': info.compress_type,
                'header_offset': header_offset,
                'data_offset': data_offset,
            })
        
    # Read the bag-info.txt and signed-metadata.json
    bag_info = (bag_dir / 'bag-info.txt').read_text()
    signed_metadata = json.loads((bag_dir / 'data/signed-metadata.json').read_text())

    return {
        'bag_info': bag_info,
        'signed_metadata': signed_metadata,
        'zip_entries': zip_info
    }

def upload_archive(output_path, collection_path, metadata_path, s3_path, session_args):
    s3 = boto3.Session(**session_args).client('s3')
    bucket_name, s3_path = s3_path.split('/', 1)

    # Upload zip file
    s3_collection_key = os.path.join(s3_path, str(collection_path.relative_to(output_path)))
    s3.upload_file(str(collection_path), bucket_name, s3_collection_key)
    logger.info(f"  - Uploaded {collection_path.relative_to(output_path)} to {s3_collection_key}")

    # Upload metadata file
    s3_metadata_key = os.path.join(s3_path, str(metadata_path.relative_to(output_path)))
    s3.upload_file(str(metadata_path), bucket_name, s3_metadata_key)
    logger.info(f"  - Uploaded {metadata_path.relative_to(output_path)} to {s3_metadata_key}")


def run_pipeline(
        dataset: Dataset, 
        output_path: Path, 
        metadata_path: Path, 
        collection_path: Path, 
        signatures: list = None,
        session_args: dict = None,
        s3_path: str = None,
        no_delete: bool = False,
    ):
    logger.info(f"Processing dataset: {dataset.name}")
    
    # we have a db forked from the main process, so we need to close it and reopen if needed
    db.close()

    # set this here so it makes it into the metadata
    dataset.crawler_downloaded_date = datetime.now()

    with tempfile.TemporaryDirectory(dir=str(output_path)) as temp_dir:
        logger.info("- Creating archive...")
        # set up paths
        temp_dir = Path(temp_dir)
        bag_dir = temp_dir / 'bag'
        archive_path = temp_dir / 'archive.zip'

        # download data with nabit
        create_archive(bag_dir, dataset, signatures)

        logger.info("- Zipping archive...")
        # zip up data and create metadata
        output_metadata = zip_archive(bag_dir, archive_path)

        logger.info("- Moving files to final location...")
        # Move files to final location
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        os.rename(str(archive_path), collection_path)
        metadata_path.write_text(json.dumps(output_metadata) + '\n')

    if s3_path:
        logger.info("Uploading to S3...")
        upload_archive(output_path, collection_path, metadata_path, s3_path, session_args)

    if not no_delete:
        logger.info("- Deleting zip archive...")
        os.remove(collection_path)
        if collection_path.parent.exists() and not os.listdir(collection_path.parent):
            os.rmdir(collection_path.parent)

    logger.info("- Setting crawler_downloaded_date...")
    db.connect()
    dataset.save()
    
    logger.info("Processing complete")

def get_unprocessed_datasets(output_path: Path, collection: str, min_size: int = 0, dataset_name: str = None):
    """Get datasets from SQLite that don't have metadata files yet."""
    query = Dataset.select()
    
    if dataset_name:
        query = query.where(Dataset.name == dataset_name)
    if min_size:
        query = query.where(Dataset.size >= min_size)

    # Initialize progress bars
    stats_counter['total'] = tqdm(desc="Total records", unit="pkg")
    stats_counter['skipped'] = tqdm(desc="Already processed", unit="pkg")
    stats_counter['yielded'] = tqdm(desc="Processing", unit="pkg")

    for dataset in query:
        stats_counter['total'].update(1)
        
        # Check if metadata file exists
        name = dataset.name
        metadata_path = output_path / 'metadata' / collection / name / 'v1.json'
        
        if metadata_path.exists():
            stats_counter['skipped'].update(1)
            continue
            
        stats_counter['yielded'].update(1)
        yield dataset


@click.command()
@click.option('--db-path', '-d', type=click.Path(exists=True, path_type=Path), default='data/data.db')
@click.option('--output-path', '-o', type=click.Path(path_type=Path), default='data/processed',
              help='Output path.')
@click.option('--collection', '-c', type=str, default='data_gov',
              help='Collection name.')
@click.option('--workers', '-w', type=int, default=None, 
              help='Number of worker processes. Defaults to CPU count.')
@click.option('--min-size', '-s', type=int, default=0,
              help='Minimum size of dataset to process.')
@click.option('--dataset-name', help='Dataset name to process.')
@click.option('--if-exists', '-e', type=click.Choice(['skip', 'replace', 'version']), default='skip',
              help='Whether to skip, replace, or add a version if dataset already exists.')
@click.option('--signatures', help='JSON string of signature configuration.')
@click.option('--profile', '-p', help='AWS profile name')
@click.option('--s3-path', '-s', help='S3 path for uploads, e.g. "<bucket_name>/<path>"')
@click.option('--log-level', '-l', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), default=None,
              help='Logging level.')
@click.option('--stop-after', help='Stop after processing this many collections', type=int)
@click.option('--no-delete', is_flag=True, help='Set to preserve zipped data on disk as well as metadata')
def main(db_path: Path, output_path: Path, collection: str, workers=None, min_size=0, dataset_name=None,
         if_exists='skip', signatures=None, profile=None, s3_path=None, log_level=None, stop_after=None, no_delete=False):
    
    if dataset_name:
        workers = 1
        stop_after = 1

    if signatures:
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

    session_args = {}
    if profile:
        session_args['profile_name'] = profile

    # Initialize database connection
    db.init(db_path)
    db.connect()

    def get_tasks():
        processed = 0
        for dataset in get_unprocessed_datasets(output_path, collection, min_size, dataset_name):
            # handle existing datasets
            name = dataset.name
            collection_path = output_path / 'collections' / collection / name / 'v1.zip'
            metadata_path = output_path / 'metadata' / collection / name / 'v1.json'
            
            if metadata_path.exists():
                if if_exists == 'skip':
                    continue
                elif if_exists == 'replace':
                    metadata_path.unlink()
                    if collection_path.exists():
                        collection_path.unlink()
                elif if_exists == 'version':
                    version = 2
                    while True:
                        collection_path = output_path / 'collections' / collection / name / f'v{version}.zip'
                        metadata_path = output_path / 'metadata' / collection / name / f'v{version}.json'
                        if not metadata_path.exists():
                            break
                        version += 1

            yield dataset, output_path, metadata_path, collection_path, signatures, session_args, s3_path, no_delete

            processed += 1
            if stop_after and processed >= stop_after:
                break

    try:
        run_parallel(run_pipeline, get_tasks(), workers, log_level=log_level, catch_errors=False)
    finally:
        # Close progress bars
        for counter in stats_counter.values():
            counter.close()
        db.close()

if __name__ == '__main__':
    main()
