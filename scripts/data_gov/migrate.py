from playhouse.migrate import *
from scripts.data_gov.models import db, Crawl

migrator = SqliteMigrator(db)

def do_migrate():
    crawler_last_run_id = ForeignKeyField(Crawl, null=True)
    deleted_by = ForeignKeyField(Crawl, null=True)
    
    with db.atomic():
        # Create the Run table first
        db.create_tables([Crawl])
        
        migrate(
            migrator.add_column('dataset', 'crawler_last_run_id', crawler_last_run_id),
            migrator.add_column('datasethistory', 'deleted_by', deleted_by),
        )

if __name__ == '__main__':
    do_migrate()