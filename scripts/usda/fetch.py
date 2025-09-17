# crawl three sources: NAD, OALJ, and OJO

# OALJ:
# all PDFs linked from https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/services/oalj-decisions
# all html linked from https://usda-nad-local1.entellitrak.com/etk-usda-nad-prod-temp/page.request.do?page=page.serachdeterminationalj&type=oalj
# for the html, we think you can get all 208 by hitting enter in a blank date field; you only get 198 by clicking the "submit" button

# OJO:
# all PDFs linked from https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/office-judicial-officer/ojo-decisions
# all html linked from https://usda-nad-local1.entellitrak.com/etk-usda-nad-prod-temp/page.request.do?page=page.serachdeterminationalj&type=ojo
# (note the html link seems to actually serve exactly the same as the OALJ link)

# NAD:
# all html linked from https://usda-nad-local1.entellitrak.com/etk-usda-nad-prod-temp/page.request.do?page=page.searchDeterminations.styled

# potentially include volume publications:
# https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/services/agriculture-decisions-archive
# https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/services/agriculture-decisions-publication
# https://nationalaglawcenter.org/aglaw-reporter/usdadecisions/
# https://archive.org/details/pub_united-states-dept-of-agriculture-agriculture-decisions

import click
import json
import logging
from pathlib import Path
from pyquery import PyQuery as pq
from urllib.parse import urljoin
from tqdm import tqdm
import re
from scripts.helpers.misc import cached_requests_session


logger = logging.getLogger(__name__)

BASE_URL = "https://usda-nad-local1.entellitrak.com/etk-usda-nad-prod-temp/"
NAD_SEARCH_URL = urljoin(BASE_URL, "page.request.do?page=page.searchDeterminations.styled")
OALJ_OJO_SEARCH_URL = urljoin(BASE_URL, "page.request.do?page=page.serachdeterminationalj")
OALJ_PDFS_URL = "https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/services/oalj-decisions"
OJO_PDFS_URL = "https://www.usda.gov/about-usda/general-information/staff-offices/office-hearings-and-appeals/office-judicial-officer/ojo-decisions"
NAD_AGENCIES = ["FSA", "N/A", "NRCS", "RBCS", "RD", "RMA", "RUS"]

def fetch_html(url, queries, fields):
    session = cached_requests_session(allowable_methods=["GET", "POST"])
    results = []
    for query in tqdm(queries, desc="Fetching"):
        logger.info(f"Fetching {url} with {query}")
        response = session.post(url, data=query)
        response.raise_for_status()

        # remove xml declaration and dtd so we can parse with pyquery
        text = re.sub(r'<\?xml.*?dtd">', '', response.text, flags=re.S)

        # extract results
        d = pq(text, parser='html')
        for row in d('tr.resultsTableCells').items():
            href = urljoin(url, row('td:first-child a').attr('href'))
            cells = [c.text() for c in row('td').items()]
            results.append({
                "href": href,
                **{k: v for k, v in zip(fields, cells)},
            })

        logger.info(f"- Found {len(results)} decisions so far")

    return results

def fetch_nad_html():
    return fetch_html(
        url=NAD_SEARCH_URL,
        queries=[{
            'username': 'visitor',
            'password': 'visitor1!',
            'service': 'page.request.do?page=page.searchDeterminations.styled',
            'typeOfSearch': 'Advanced Search',
            'caseNumber': '',
            'keyword': '',
            'condition': 'and',
            'keyword2': '',
            'agency': agency,
            'decision': 'All',
            'decisionby': '0',
            'equitablerelief': '-1',
            'citation': '',
            'date': '',
            'endDate': '',
            'Advanced Search': 'Submit'
        } for agency in NAD_AGENCIES],
        fields=["filename", "date", "agency", "program", "case_id", "decision_type"],
    )

def fetch_oalj_ojo_html():
    return fetch_html(
        url=OALJ_OJO_SEARCH_URL,
        queries=[{
            'username': 'visitor',
            'password': 'visitor1!',
            'service': 'page.request.do?page=page.serachdeterminationalj',
            'typeOfSearch': 'Search',
            'caseNumber': '',
            'search': '',
            'keyword': '',
            'condition': 'and',
            'keyword2': '',
            'act': 'All',
            'decision': 'All',
            'citation': '',
            'date': '',
            'endDate': ''
        }],
        fields=["filename", "date", "agency", "case_name", "act", "docket_id", "decision_type"],
    )

def fix_nbsp(text):
    return re.sub(r'\s*\xa0+\s*', ' ', text)

def fetch_pdfs(url):
    """Fetches PDF links and metadata from a decisions page."""
    session = cached_requests_session()
    # necessary to get the page to load
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:137.0) Gecko/20100101 Firefox/137.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    response = session.get(url, headers=headers)
    response.raise_for_status()

    d = pq(response.content)
    results = []

    # parse out groups of PDF links that look like this:
    # <dl class="ckeditor-accordion">
    # <dt><strong>2016&nbsp;Initial Decisions</strong></dt>
    # ...
    # <tr>
    #    <td>15/02/06</td>
    #    <td><a href="....pdf">case name</a></td>
    #    <td>docket number</td>
    #    <td>act</td>
    # </tr>
    #  ... or ...
    #    <li><a href="...pdf">some title</a></li>
    for container in tqdm(d('dl.ckeditor-accordion').items(), desc="Parsing OALJ PDFs"):
        subcategory = fix_nbsp(container('dt').text().strip())
        category = subcategory.split(' ', 1)[1]  # strip the year from the subcategory

        for link in container('a[href$=".pdf"]').items():
            href = urljoin(OALJ_PDFS_URL, link.attr('href'))
            data = {
                "href": href,
                "category": category,
                "subcategory": subcategory,
            }

            # Check if link is inside a table row
            tr_parent = link.closest('tr')
            if tr_parent:
                td_texts = [td.text().strip() for td in tr_parent('td').items()]
                data['date_filed'] = td_texts[0]
                data['case_name'] = fix_nbsp(td_texts[1])
                data['docket_number'] = td_texts[2]
                data['act'] = td_texts[3]
            else:
                data['text'] = fix_nbsp(link.text().strip())

            results.append(data)

    logger.info(f"- Found {len(results)} PDF links")
    return results


@click.command()
@click.argument('output_path', type=click.Path(path_type=Path), default='data/usda/index.json')
def main(output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        index = json.loads(output_path.read_text())
    else:
        index = {
            "nad_html": [],
            "oalj_ojo_html": [],
            "oalj_pdfs": [],
            "ojo_pdfs": [],
        }

    index["oalj_pdfs"] = fetch_pdfs(OALJ_PDFS_URL)
    index["ojo_pdfs"] = fetch_pdfs(OJO_PDFS_URL)
    index["nad_html"] = fetch_nad_html()
    index["oalj_ojo_html"] = fetch_oalj_ojo_html()
    output_path.write_text(json.dumps(index, indent=2))

if __name__ == '__main__':
    main()
