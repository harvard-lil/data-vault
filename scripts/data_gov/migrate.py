from playhouse.migrate import *
from scripts.data_gov.models import db

migrator = SqliteMigrator(db)

def do_migrate():
    crawler_identified_date = DateTimeField(null=True)
    crawler_downloaded_date = DateTimeField(null=True)
    with db.atomic():
        migrate(
            # migrator.add_column('dataset', 'crawler_identified_date', crawler_identified_date),
            # migrator.add_column('dataset', 'crawler_downloaded_date', crawler_downloaded_date),
            # migrator.add_column('datasethistory', 'crawler_identified_date', crawler_identified_date),
            # migrator.add_column('datasethistory', 'crawler_downloaded_date', crawler_downloaded_date),
        )

if __name__ == '__main__':
    do_migrate()