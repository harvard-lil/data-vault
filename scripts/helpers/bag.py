import os
import json
import zipfile
import struct
import boto3
import logging
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
from nabit.lib.archive import package

logger = logging.getLogger(__name__)

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

def zip_archive(bag_dir, archive_path):
    """Zip up a nabit archive and create metadata."""
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
    """Upload archive and metadata to S3."""
    s3 = boto3.Session(**session_args).client('s3')
    bucket_name, s3_key_prefix = s3_path.split('/', 1)

    # Upload zip file
    s3_collection_key = os.path.join(s3_key_prefix, str(collection_path.relative_to(output_path)))
    s3.upload_file(str(collection_path), bucket_name, s3_collection_key)
    logger.info(f"  - Uploaded {collection_path.relative_to(output_path)} to {s3_collection_key}")

    # Upload metadata file
    s3_metadata_key = os.path.join(s3_key_prefix, str(metadata_path.relative_to(output_path)))
    s3.upload_file(str(metadata_path), bucket_name, s3_metadata_key)
    logger.info(f"  - Uploaded {metadata_path.relative_to(output_path)} to {s3_metadata_key}")

def cleanup_files(collection_path, no_delete=False, s3_path=None):
    """Clean up local files after upload if needed."""
    if not no_delete and s3_path:
        logger.info("- Deleting local zip archive...")
        if os.path.exists(collection_path):
            os.remove(collection_path)
            if collection_path.parent.exists() and not os.listdir(collection_path.parent):
                os.rmdir(collection_path.parent)

def fetch_and_upload(
        output_path,
        collection_path,
        metadata_path,
        create_archive_callback,
        signatures=None,
        session_args=None,
        s3_path=None,
        no_delete=False,
    ):
    """
    Common pipeline for creating and processing archives.
    
    Args:
        output_path: Base output directory
        collection_path: Path where the final zip will be stored
        metadata_path: Path where the metadata will be stored
        create_archive_callback: Function that will create the archive
        signatures: Signature configuration for nabit
        session_args: AWS session arguments
        s3_path: S3 path for uploads
        no_delete: Whether to preserve local files
    """
    with tempfile.TemporaryDirectory(dir=str(output_path)) as temp_dir:
        logger.info("- Creating archive...")
        # set up paths
        temp_dir = Path(temp_dir)
        bag_dir = temp_dir / 'bag'
        archive_path = temp_dir / 'archive.zip'
        source_files_dir = temp_dir / 'source_files'
        source_files_dir.mkdir(parents=True, exist_ok=True)

        # Call the callback to create the archive
        package_kwargs = create_archive_callback(source_files_dir)

        # create bag
        package(
            output_path=bag_dir,
            collect_errors='ignore',
            signatures=signatures,
            **package_kwargs,
        )

        logger.info("- Zipping archive...")
        # zip up data and create metadata
        output_metadata = zip_archive(bag_dir, archive_path)

        logger.info("- Moving files to final location...")
        # Move files to final location
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archive_path), collection_path)
        with open(metadata_path, 'w') as f:
            json.dump(output_metadata, f)
            f.write('\n')

    if s3_path:
        logger.info("Uploading to S3...")
        upload_archive(output_path, collection_path, metadata_path, s3_path, session_args)

    cleanup_files(collection_path, no_delete, s3_path) 