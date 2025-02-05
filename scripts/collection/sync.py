import boto3
import click
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@click.command()
@click.option('--collections-file', '-c', type=click.Path(exists=True, path_type=Path),
              default='collections/collections.json',
              help='Path to collections configuration file.')
def main(collections_file: Path):
    # Load collections config
    collections = json.loads(collections_file.read_text())
    collections_dir = collections_file.parent

    for collection in collections:
        s3 = boto3.Session(profile_name=collection['aws_profile']).client('s3')
        collection_path = collections_dir / collection['directory']
        bucket_name, s3_prefix = collection['s3_path'].split('/', 1)

        for file_path in collection_path.rglob('*'):
            if file_path.is_file():
                relative_path = file_path.relative_to(collection_path)
                s3_key = f"{s3_prefix}/{relative_path}"
                print(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
                s3.upload_file(str(file_path), bucket_name, s3_key)

if __name__ == '__main__':
    main()
