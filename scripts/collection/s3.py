import boto3
import click
from tqdm import tqdm
import logging
import json
import tempfile
import os
from scripts.helpers.misc import json_default
import zipfile
from scripts.helpers.onepassword import save_item, share_item

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
def undelete(s3_path: str, profile: str = None, dry_run: bool = False):
    """Remove delete markers from versioned S3 objects, effectively undeleting them."""
    bucket, prefix = s3_path.split('/', 1)
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    remove_delete_markers(s3_client, bucket, prefix, dry_run)

@cli.command()
@click.argument('s3_path')
@click.option('--profile', help='AWS profile name', default='sc-direct')
@click.option('--dry-run', is_flag=True, help='Show what would be done without actually doing it')
def delete_empty(s3_path: str, profile: str = None, dry_run: bool = False):
    """Delete all zero-size objects under the given prefix."""
    bucket, prefix = s3_path.split('/', 1)
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    delete_empty_files(s3_client, bucket, prefix, dry_run)

@cli.command()
@click.argument('s3_path')
@click.option('--profile', help='AWS profile name', default='sc-direct')
@click.option('--output', '-o', help='Output path for index file', default=None)
def write_index(s3_path: str, profile: str = None, output: str | None = None):
    """Write a JSONL index of all files under the given prefix."""
    bucket, prefix = s3_path.split('/', 1)
    
    if output is None:
        output = prefix.rstrip('/') + '/file_listing.jsonl.zip'
    
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    write_file_listing(s3_client, bucket, prefix, output)

@cli.command()
@click.argument('bucket_name')
@click.option('--profile', '-p', help='AWS profile name')
@click.option('--region', '-r', help='AWS region', default='us-east-1')
@click.option('--tag', '-t', help='Tag the bucket with a name', default=None)
def create_bucket(bucket_name: str, profile: str = None, region: str = 'us-east-1', tag: str | None = None):
    """Create a new S3 bucket with versioning enabled by default."""
    session = boto3.Session(profile_name=profile)
    s3_client = session.client('s3')
    
    # Ensure bucket exists
    try:
        if region == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': region},
            )
    except s3_client.exceptions.BucketAlreadyExists:
        logger.warning(f"Bucket {bucket_name} already exists. Updating settings.")

    # Configure bucket
    s3_client.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={'Status': 'Enabled'}
    )
    
    logger.info(f"Ensured bucket {bucket_name} exists with versioning enabled")

@cli.command()
@click.argument('bucket_name')
@click.argument('username')
@click.option('--profile', '-p', help='AWS profile name')
@click.option('--permissions-boundary', '-b', help='ARN of the permissions boundary policy')
@click.option('--op-vault', help='1Password vault to store credentials in', default='Private')
@click.option('--op-share', help='Share the credentials with the given email', default=None)
def create_user(bucket_name: str, username: str, profile: str, permissions_boundary: str, op_vault: str, op_share: str | None):
    """Generate temporary S3 credentials with read/write/list access for a specific bucket."""
    session = boto3.Session(profile_name=profile)
    iam_client = session.client('iam')
    
    # Define inline policy for bucket access
    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*"
                ]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:ListAllMyBuckets"
                ],
                "Resource": [
                    "arn:aws:s3:::*"
                ]
            }
        ]
    }
    
    # Create the IAM user with permissions boundary
    try:
        iam_client.create_user(
            UserName=username,
            PermissionsBoundary=permissions_boundary
        )
        logger.info(f"Created IAM user: {username}")
    except iam_client.exceptions.EntityAlreadyExistsException:
        logger.warning(f"User {username} already exists")
        
    # Attach inline policy directly to user
    iam_client.put_user_policy(
        UserName=username,
        PolicyName=f"{bucket_name}-access",
        PolicyDocument=json.dumps(bucket_policy)
    )
    logger.info(f"Attached bucket access policy to user {username}")
    
    # Create access key for the user
    response = iam_client.create_access_key(UserName=username)
    credentials = response['AccessKey']
    
    # Output the credentials
    click.echo(f"AWS_ACCESS_KEY_ID={credentials['AccessKeyId']}")
    click.echo(f"AWS_SECRET_ACCESS_KEY={credentials['SecretAccessKey']}")
    
    # Save credentials to 1Password if requested
    if op_vault:
        item = save_item(op_vault, f"{username} S3 Credentials for {bucket_name}", [
            {
                'title': 'Access Key ID',
                'value': credentials['AccessKeyId'],
                'section_id': 's3_details'
            },
            {
                'title': 'Secret Access Key',
                'value': credentials['SecretAccessKey'],
                'section_id': 's3_details'
            },
            {
                'title': 'S3 Bucket',
                'value': bucket_name,
                'section_id': 's3_details'
            },
        ])
        if op_share:
            share_link = share_item(item, [op_share])
            click.echo(f"To share credentials with {op_share}, use the following link: {share_link}")

        
if __name__ == '__main__':
    cli()


