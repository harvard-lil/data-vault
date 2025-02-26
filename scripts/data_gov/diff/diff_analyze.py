import json
from collections import Counter, defaultdict
from pathlib import Path


if __name__ == "__main__":

     # Read the JSONL file and count crawler_identified_date values
     downloaded_counts = Counter()
     identified_counts = Counter()
     titles_by_org = defaultdict(list)
     with open('data/data_db_dump_20250130.only_name.jsonl', 'r') as f:
          for line in f:
               data = json.loads(line)
               org = json.loads(data.get('organization', '{}'))
               identified_counts[(data.get('crawler_identified_date') or '')[:10]] += 1
               titles_by_org[org['title']].append(data["title"])

     # Print the counts sorted by date
     for date, count in sorted(identified_counts.items()):
          print(f"{date}: {count}")

     # sort each list of titles by org
     for org, titles in titles_by_org.items():
          titles_by_org[org].sort()
     Path('data/titles_by_org.json').write_text(json.dumps(titles_by_org, indent=2))


     # print urls
     for path in Path('data/').glob('glass*'):
          print(path)
          with open(path, 'r') as f:
               for line in f:
                    data = json.loads(line)
                    print("* " + data['name'])
                    resources = data.get('resources', [])
                    if type(resources) == str:
                         resources = json.loads(resources)
                    for resource in resources:
                         print(' * ' + resource['url'])
