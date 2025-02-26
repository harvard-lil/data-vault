import click
from pathlib import Path
from scripts.data_gov.models import db, Dataset
import logging
from tqdm import tqdm

logger = logging.getLogger(__name__)


# Header template with styles
HEADER_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>Data.gov Dataset Mirror</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <h1>Data.gov Dataset Mirror</h1>
'''

TABLE_START = '''    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Organization</th>
                <th>Description</th>
            </tr>
        </thead>
        <tbody>
'''

ROW_TEMPLATE = '''            <tr>
                <td>{name}</td>
                <td>{org}</td>
                <td>{title}</td>
            </tr>
'''

TABLE_END = '''        </tbody>
    </table>
</body>
</html>
'''

def render_html(datasets_query, output_path: Path) -> None:
    """Render the datasets to an HTML file, streaming content."""
    with open(output_path / 'index.html', 'w', encoding='utf-8') as f:
        # Write header
        f.write(HEADER_TEMPLATE)
        
        # Write table start
        f.write(TABLE_START)
        
        # Stream each dataset row
        rows = []
        for dataset in tqdm(datasets_query.iterator(), desc="Rendering datasets"):
            org_title = dataset.organization.get('title') if dataset.organization else 'N/A'
            row = ROW_TEMPLATE.format(
                name=dataset.name or '',
                org=org_title,
                title=dataset.title,
            )
            rows.append(row)
            if len(rows) >= 1000:
                f.write('\n'.join(rows))
                rows = []

        if rows:
            f.write('\n'.join(rows))
        
        # Write table end
        f.write(TABLE_END)

@click.command()
@click.argument('db_path', type=click.Path(path_type=Path), default='data/data.db')
@click.argument('output_path', type=click.Path(path_type=Path), default='data/processed/web')
@click.option('--limit', '-n', type=int, default=None,
              help='Maximum number of rows to display. Default: all rows.')
def main(db_path: Path, output_path: Path, limit: int | None):
    """Render the Dataset table to an HTML file."""
    
    logger.info(f"Connecting to database at {db_path}")
    db.init(db_path)
    db.connect()
    
    try:
        logger.info("Starting HTML generation...")
        datasets_query = Dataset.select().order_by(Dataset.id)
        if limit:
            datasets_query = datasets_query.limit(limit)
            logger.info(f"Limited to {limit} rows")
        
        logger.info(f"Rendering HTML to {output_path}")
        render_html(datasets_query, output_path)
        logger.info("Done!")
        
    finally:
        db.close()

if __name__ == "__main__":
    main()
