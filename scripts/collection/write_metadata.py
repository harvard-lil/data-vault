import boto3
import click
import json
from pathlib import Path
import logging
import csv
import zipfile
from tqdm import tqdm
import io

logger = logging.getLogger(__name__)

@click.group()
def cli():
    pass

@cli.command()
@click.option('--collections-file', '-c', type=click.Path(exists=True, path_type=Path),
              default='collections/collections.json',
              help='Path to collections configuration file.')
def write_readme(collections_file: Path):
    # Load collections config
    collections = json.loads(collections_file.read_text())
    collections_dir = collections_file.parent

    for collection in collections:
        s3 = boto3.Session(profile_name=collection['aws_profile']).client('s3')
        collection_path = collections_dir / collection['directory']
        bucket_name, s3_prefix = collection['s3_path'].split('/', 1)

        for file_path in collection_path.rglob('*'):
            # Skip dotfiles and files in dot directories
            if any(part.startswith('.') for part in file_path.parts):
                continue
                
            if file_path.is_file():
                relative_path = file_path.relative_to(collection_path)
                s3_key = f"{s3_prefix}/{relative_path}"
                print(f"Uploading {file_path} to s3://{bucket_name}/{s3_key}")
                s3.upload_file(str(file_path), bucket_name, s3_key)

@cli.command()
@click.argument('metadata_file', type=click.Path(exists=True, path_type=Path))
@click.argument('output_file', type=click.Path(path_type=Path))
def write_csv(metadata_file: Path, output_file: Path):
    """
    Read a zipped JSONL file of metadata and write dataset info to a zipped CSV.
    
    metadata_file: Path to the zip file containing metadata JSONL
    output_file: Path where the zipped CSV should be written
    """
    # Get the base filename without .zip extension for the internal CSV file
    internal_filename = output_file.name.replace('.zip', '')
    jsonl_name = metadata_file.name.replace('.zip', '')
    
    with zipfile.ZipFile(metadata_file, 'r') as input_zf, \
         zipfile.ZipFile(output_file, 'w', compression=zipfile.ZIP_DEFLATED) as output_zf, \
         output_zf.open(internal_filename, 'w', force_zip64=True) as csvfile, \
         input_zf.open(jsonl_name) as jsonlfile:
         
        # Create a text wrapper around the binary file
        text_wrapper = io.TextIOWrapper(csvfile, write_through=True, newline='')
        writer = csv.writer(text_wrapper)
        writer.writerow(['name', 'organization', 'title', 'date', 'metadata_path', 'collection_path'])
            
        # Read from input zip and write to output zip
        for line in tqdm(jsonlfile, desc="Writing CSV"):
            metadata = json.loads(line)
            dataset_info = metadata['signed_metadata']['data_gov_metadata']
            if dataset_info:
                writer.writerow([
                    dataset_info['name'],
                    dataset_info['organization']['title'],
                    dataset_info['title'],
                    dataset_info['metadata_modified'],
                    metadata['metadata_path'],
                    metadata['collection_path'],
                ])

@cli.command()
@click.argument('metadata_dir', type=click.Path(exists=True, path_type=Path))
@click.argument('output_file', type=click.Path(path_type=Path))
def write_jsonl(metadata_dir: Path, output_file: Path):
    """
    Read each .json file, recursively, in metadata directory and write to a single compressed zipped JSONL file.
    All records are written to a single JSONL file within the zip, named same as output_file without .zip
    """
    # Get the base filename without .zip extension for the internal file
    internal_filename = output_file.name.replace('.zip', '')
    output_dir = output_file.parent
    
    with zipfile.ZipFile(output_file, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        # Create a single file in the zip archive
        with zf.open(internal_filename, 'w', force_zip64=True) as f:
            # Iterate through all JSON files
            for file_path in tqdm(metadata_dir.rglob('*.json'), desc="Writing JSONL"):
                with open(file_path, 'r') as json_file:
                    metadata = json.load(json_file)
                    metadata['metadata_path'] = str(file_path.relative_to(output_dir))
                    metadata['collection_path'] = metadata['metadata_path'].replace('metadata', 'collections', 1)
                    # Write each record to the same file, with newline
                    f.write((json.dumps(metadata) + '\n').encode('utf-8'))

if __name__ == '__main__':
    cli()
