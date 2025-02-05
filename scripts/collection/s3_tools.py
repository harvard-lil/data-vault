import boto3
import click
from tqdm import tqdm
import logging
from itertools import islice
import json
import gzip
from io import BytesIO
import tempfile
import os
from scripts.helpers.misc import json_default
import zipfile

logger = logging.getLogger(__name__)

def get_delete_markers(s3_client, bucket: str, prefix: str):
    """Get all delete markers for objects with the given prefix."""
    paginator = s3_client.get_paginator('list_object_versions')
    for page in tqdm(paginator.paginate(Bucket=bucket, Prefix=prefix), desc="pages"):
        if 'DeleteMarkers' in page:
            yield [
                {
                    'Key': marker['Key'],
                    'VersionId': marker['VersionId']
                }
                for marker in page['DeleteMarkers']
                if marker['IsLatest']
            ]

def remove_delete_markers(s3_client, bucket: str, prefix: str, dry_run: bool = False):
    """Remove all delete markers for objects with the given prefix."""
    for marker_batch in get_delete_markers(s3_client, bucket, prefix):
        response = s3_client.delete_objects(
            Bucket=bucket,
            Delete={
                'Objects': marker_batch,
                'Quiet': True
            }
        )
        
        # Log any errors
        if 'Errors' in response:
            for error in response['Errors']:
                logger.error(f"Failed to remove marker for {error['Key']}: {error['Message']}")

def get_empty_files(s3_client, bucket: str, prefix: str):
    """Get all objects with size zero under the given prefix."""
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in tqdm(paginator.paginate(Bucket=bucket, Prefix=prefix), desc="pages"):
        if 'Contents' in page:
            yield [
                {'Key': obj['Key']}
                for obj in page['Contents']
                if obj['Size'] == 0
            ]

def delete_empty_files(s3_client, bucket: str, prefix: str, dry_run: bool = False):
    """Delete all zero-size objects under the given prefix."""
    pbar = tqdm(desc="deleted")
    for empty_batch in get_empty_files(s3_client, bucket, prefix):
        if not empty_batch:
            continue

        if dry_run:
            for obj in empty_batch:
                logger.info(f"Would delete empty file: {obj['Key']}")
            continue

        pbar.update(len(empty_batch))

        response = s3_client.delete_objects(
            Bucket=bucket,
            Delete={
                'Objects': empty_batch,
                'Quiet': True
            }
        )
        
        # Log any errors
        if 'Errors' in response:
            for error in response['Errors']:
                logger.error(f"Failed to delete {error['Key']}: {error['Message']}")

    pbar.close()

def write_file_listing(s3_client, bucket: str, prefix: str, index_key: str):
    """Write a JSONL listing of all files under prefix to index_key."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.zip', delete=True) as tmp:
        with zipfile.ZipFile(tmp, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            # Create a temporary file for the JSONL content
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=True) as jsonl:
                paginator = s3_client.get_paginator('list_objects_v2')
                for page in tqdm(paginator.paginate(Bucket=bucket, Prefix=prefix), desc="indexing"):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Write each object as a JSON line using custom encoder
                            line = json.dumps(obj, default=json_default) + '\n'
                            jsonl.write(line)
                
                # Flush the JSONL file and add it to the zip
                jsonl.flush()
                zf.write(jsonl.name, arcname='file_listing.jsonl')
        
        # Upload the zip file
        tmp.flush()
        s3_client.upload_file(
            tmp.name,
            bucket,
            index_key,
            ExtraArgs={'ContentType': 'application/zip'}
        )
    
    logger.info(f"Wrote index to s3://{bucket}/{index_key}")

@click.group()
def cli():
    """S3 object management commands."""
    pass

@cli.command()
@click.argument('s3_path')
@click.option('--profile', help='AWS profile name', default='sc-direct')
@click.option('--dry-run', is_flag=True, help='Show what would be done without actually doing it')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO', help='Set logging level')
def undelete(s3_path: str, profile: str = None, dry_run: bool = False, log_level: str = 'INFO'):
    """Remove delete markers from versioned S3 objects, effectively undeleting them."""
    logging.basicConfig(level=log_level)
    bucket, prefix = s3_path.split('/', 1)
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    remove_delete_markers(s3_client, bucket, prefix, dry_run)

@cli.command()
@click.argument('s3_path')
@click.option('--profile', help='AWS profile name', default='sc-direct')
@click.option('--dry-run', is_flag=True, help='Show what would be done without actually doing it')
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO', help='Set logging level')
def delete_empty(s3_path: str, profile: str = None, dry_run: bool = False, log_level: str = 'INFO'):
    """Delete all zero-size objects under the given prefix."""
    logging.basicConfig(level=log_level)
    bucket, prefix = s3_path.split('/', 1)
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    delete_empty_files(s3_client, bucket, prefix, dry_run)

@cli.command()
@click.argument('s3_path')
@click.option('--profile', help='AWS profile name', default='sc-direct')
@click.option('--output', '-o', help='Output path for index file', default=None)
@click.option('--log-level', type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO', help='Set logging level')
def write_index(s3_path: str, profile: str = None, output: str | None = None, log_level: str = 'INFO'):
    """Write a JSONL index of all files under the given prefix."""
    logging.basicConfig(level=log_level)
    bucket, prefix = s3_path.split('/', 1)
    
    if output is None:
        output = prefix.rstrip('/') + '/file_listing.jsonl.zip'
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    write_file_listing(s3_client, bucket, prefix, output)

if __name__ == '__main__':
    cli()

