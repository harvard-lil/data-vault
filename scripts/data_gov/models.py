from peewee import *
from playhouse.sqlite_ext import JSONField
from pathlib import Path
from datetime import datetime

db = SqliteDatabase(Path(__file__).parent.parent.parent / 'data/data.db', pragmas={
    # tuning suggested by Claude:
    'journal_mode': 'wal',          # Write-Ahead Logging for better concurrency
    'cache_size': -1024 * 64,       # 64MB cache (negative number means kibibytes)
    'synchronous': 'normal',        # Good balance between safety and speed
    'busy_timeout': 30000,          # Wait up to 30 seconds when database is locked
    'temp_store': 'memory',         # Store temp tables in memory
    'mmap_size': 268435456,         # Memory-mapped I/O (256MB)
    'page_size': 4096,              # Optimal for most systems
})

class BaseModel(Model):
    class Meta:
        database = db

class Crawl(BaseModel):
    id = AutoField(primary_key=True)
    start_date = DateTimeField()
    end_date = DateTimeField(null=True)
    

class Dataset(BaseModel):
    # fields from data.gov
    id = CharField(primary_key=True)
    name = CharField(null=True)
    title = CharField(null=True)
    notes = TextField(null=True)
    metadata_created = DateTimeField(null=True)
    metadata_modified = DateTimeField(null=True)
    private = BooleanField(null=True)
    state = CharField(null=True)
    version = CharField(null=True)
    type = CharField(null=True)
    num_resources = IntegerField(null=True)
    num_tags = IntegerField(null=True)
    isopen = BooleanField(null=True)
    author = CharField(null=True)
    author_email = CharField(null=True)
    creator_user_id = CharField(null=True)
    license_id = CharField(null=True)
    license_url = CharField(null=True)
    license_title = CharField(null=True)
    maintainer = CharField(null=True)
    maintainer_email = CharField(null=True)
    owner_org = CharField(null=True)
    url = CharField(null=True)
    organization = JSONField(null=True)
    extras = JSONField(null=True)
    resources = JSONField(null=True)
    tags = JSONField(null=True)
    groups = JSONField(null=True)
    relationships_as_subject = JSONField(null=True)
    relationships_as_object = JSONField(null=True)

    # fields starting with crawler_ are added by our crawler
    crawler_identified_date = DateTimeField(null=True, default=datetime.now)
    crawler_downloaded_date = DateTimeField(null=True)
    crawler_last_crawl_id = ForeignKeyField('Crawl', backref='datasets', null=True)


class DatasetHistory(Dataset):
    history_id = AutoField(primary_key=True)
    id = CharField()  # Regular CharField, not primary key
    deleted_by_date = DateTimeField(null=True)
