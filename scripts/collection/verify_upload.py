from pathlib import Path
import json
import zipfile
import tempfile
import requests
import click
import logging
from nabit.bin.utils import cli_validate
logger = logging.getLogger(__name__)

def download_file(url: str, target_path: Path):
    """Download a file from URL to target path"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with target_path.open('wb') as f:
        for chunk in response.iter_content(chunk_size=2**20):
            f.write(chunk)

def verify_dataset(json_url: str, zip_url: str, output_dir: Path | None = None):
    """
    Verify a dataset by downloading and checking its JSON metadata and ZIP contents.
    If output_dir is provided, write the uncompressed contents there.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Download files
        logger.info(f"Downloading metadata from {json_url}...")
        json_path = tmpdir / "metadata.json"
        download_file(json_url, json_path)
        
        logger.info(f"Downloading archive from {zip_url}...")
        zip_path = tmpdir / "data.zip"
        download_file(zip_url, zip_path)
        
        # Load metadata
        metadata = json.loads(json_path.read_text())
        
        # Create output directory
        if not output_dir:
            output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Verify file contents
        logger.info("Verifying file contents...")
        with zip_path.open('rb') as f:
            for entry in metadata['zip_entries']:
                logger.info(f"Checking {entry['filename']}...")
                f.seek(entry['data_offset'])
                zip_data = f.read(entry['compress_size'])
                
                if entry['compress_type'] == zipfile.ZIP_STORED:
                    uncompressed = zip_data
                else:
                    decompressor = zipfile._get_decompressor(entry['compress_type'])
                    uncompressed = decompressor.decompress(zip_data)
                
                # write the file
                output_file = output_dir / entry['filename']
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(uncompressed)

        logger.info("All files extracted successfully")

        # verify dataset with nabit
        cli_validate(output_dir)
        
        # Return metadata for potential further use
        return metadata

@click.command()
@click.argument('json_url', type=str)
@click.argument('zip_url', type=str)
@click.option('--output', '-o', type=click.Path(path_type=Path), 
              help='Directory to write uncompressed files')
@click.option('--log-level', '-l', 
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']), 
              default='INFO',
              help='Logging level.')
def main(json_url: str, zip_url: str, output: Path = None, log_level: str = 'INFO'):
    """Verify dataset from JSON and ZIP URLs"""
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    verify_dataset(json_url, zip_url, output)

if __name__ == '__main__':
    main()