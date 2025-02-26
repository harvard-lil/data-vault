import logging
from pathlib import Path
import click
from cloudflare import Cloudflare
import os
from scripts.helpers.misc import load_config

logger = logging.getLogger(__name__)

def generate_temp_key(account_id: str, bucket: str, parent_access_key_id: str, token: str,
                     permission: str = "object-read-write", ttl_seconds: int = 3600,
                     prefixes: list[str] | None = None, objects: list[str] | None = None):
    """Generate a temporary R2 access key using the Cloudflare API.
    
    Args:
        account_id: Cloudflare account ID
        bucket: R2 bucket name
        parent_access_key_id: Parent access key ID
        token: Cloudflare API token
        permission: Permission level ('object-read-write' or 'object-read')
        ttl_seconds: Time-to-live in seconds
        prefixes: Optional list of key prefixes to restrict access to
        objects: Optional list of specific object keys to restrict access to
    """
    params = {
        "account_id": account_id,
        "bucket": bucket,
        "parent_access_key_id": parent_access_key_id,
        "permission": permission,
        "ttl_seconds": ttl_seconds,
    }
    
    if prefixes:
        params["prefixes"] = prefixes
    if objects:
        params["objects"] = objects
        
    return Cloudflare(api_token=token).r2.temporary_credentials.create(**params)

@click.group()
def cli():
    """Cloudflare R2 utility commands."""
    pass

@cli.command()
@click.option('--bucket', '-b', type=str, required=True,
              help='R2 bucket name.')
@click.option('--permission', '-p', type=click.Choice(['object-read-write', 'object-read']), 
              default='object-read-write',
              help='Permission level for the temporary key.')
@click.option('--ttl', '-t', type=int, default=1,
              help='Time-to-live in hours for the temporary key.')
@click.option('--prefixes', '-x', multiple=True,
              help='Key prefixes to restrict access to. Can be specified multiple times.')
@click.option('--objects', '-o', multiple=True,
              help='Specific object keys to restrict access to. Can be specified multiple times.')
def generate_key(bucket: str, permission: str, ttl: int, prefixes: tuple[str, ...], 
                objects: tuple[str, ...], log_level: str):
    """Generate temporary Cloudflare R2 access credentials."""
    
    # Load config
    config = load_config().get("temp_tokens", {})

    if not config or any(key not in config for key in ['parent_access_key_id', 'account_id', 'token']):
        raise click.ClickException("Config file must have 'temp_tokens' dict with 'parent_access_key_id', 'account_id', and 'token' keys")
    
    # Generate temporary key
    temp_cred = generate_temp_key(
        account_id=config['account_id'],
        bucket=bucket,
        parent_access_key_id=config['parent_access_key_id'],
        token=config['token'],
        permission=permission,
        ttl_seconds=ttl * 3600,
        prefixes=list(prefixes) if prefixes else None,
        objects=list(objects) if objects else None
    )
    
    # Output AWS config format
    click.echo("\n# Add this to ~/.aws/config:")
    click.echo("[profile r2-temp]")
    click.echo(f"aws_access_key_id = {temp_cred.access_key_id}")
    click.echo(f"aws_secret_access_key = {temp_cred.secret_access_key}")
    click.echo(f"aws_session_token = {temp_cred.session_token}")
    click.echo("region = auto")
    click.echo(f"endpoint_url = https://{config['account_id']}.r2.cloudflarestorage.com")

    # Output sample command using first prefix if available
    click.echo("\n# Sample upload command:")
    sample_path = objects[0] if objects else f"{prefixes[0].strip('/')}/" if prefixes else ""
    click.echo(f"aws s3 cp local-file.txt s3://{bucket}/{sample_path} --profile r2-temp")

if __name__ == "__main__":
    cli()
