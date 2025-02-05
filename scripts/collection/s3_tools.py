import boto3
import click
from tqdm import tqdm
import logging
from itertools import islice

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

if __name__ == '__main__':
    cli()

