"""Seed fictional extractor data, or remove only this demo with --delete.

Load .env into your shell first. All demo writes for one invocation are atomic.
Names, sources and timestamps are stable so repeated runs do not add evidence.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

from cli_support import CommandError, cli_entrypoint
from crawler.models import PageDocument
from database import connected_extractor
from extractor import Extractor

DEMO_DATASET = 'corporatemapper-demo-v1'


def demo_pages(dataset=DEMO_DATASET):
    """Return fictional pages; a separate namespace isolates integration tests."""
    if not re.fullmatch(r'corporatemapper-demo-[a-z0-9-]+', dataset):
        raise ValueError('Invalid demo dataset namespace.')
    base = f'https://demo.corporatemapper.invalid/{dataset}'
    groups = [
        ('Meridian Labs (Demo)', [
            ('Alex Morgan', 'Engineering Director'), ('Jordan Lee', 'Software Engineer'),
            ('Sam Taylor', 'Product Designer'), ('Casey Chen', 'Security Engineer'),
            ('Riley Patel', 'Product Manager'), ('Jamie Davis', 'Data Engineer'),
            ('Avery Wilson', 'Operations Manager'), ('Quinn Campbell', 'Research Lead'),
            ('Drew Mitchell', 'Platform Engineer'), ('Morgan Garcia', 'People Partner'),
            ('Cameron Wright', 'Customer Success Lead'), ('Blake Nguyen', 'Technical Advisor'),
        ]),
        ('Northstar Advisory (Demo)', [
            ('Reese Thompson', 'Managing Director'), ('Taylor Brooks', 'Consultant'),
            ('Robin Ellis', 'Research Analyst'), ('Sage Parker', ''),
        ]),
        (None, [('Charlie Reed', 'Independent Researcher')]),
        # Appended after the original 17, never inserted earlier: each person's
        # number (and therefore their stable URL/identity_key) must never shift,
        # or a database already seeded under the old numbering merges a new
        # person's fresh evidence with whichever old identity used to hold that number.
        ('Beacon Financial (Demo)', [
            ('Nadia Kim', 'Marketing Director'), ('Owen Bright', 'Finance Manager'),
            ('Priya Anand', 'Legal Counsel'), ('Felix Turner', 'Chief Technology Officer'),
            ('Grace Liu', 'Executive Assistant'), ('Marcus Webb', 'IT Support Specialist'),
        ]),
    ]
    pages = []
    number = 0
    for group_index, (organisation, people) in enumerate(groups):
        source = f'{base}/team-{group_index}'
        records = []
        for name, title in people:
            number += 1
            record = {
                '@type': 'Person', '@id': f'{base}/people/{number}',
                'name': name, 'url': f'{base}/people/{number}',
                'email': f'person{number}@demo.corporatemapper.invalid',
                'telephone': f'+1 202 555 {100 + number:04d}',
                'sameAs': [f'{base}/profiles/{number}'],
                'description': 'Fictional CorporateMapper demonstration record.',
            }
            if title:
                record['jobTitle'] = title
            if organisation:
                record['worksFor'] = {'@type': 'Organization', 'name': organisation}
            if name == 'Blake Nguyen':
                record['worksFor'] = [record['worksFor'], {'@type': 'Organization', 'name': 'Northstar Advisory (Demo)'}]
            records.append(record)
        pages.append(PageDocument(
            url=source, final_url=source, status_code=200, content_type='text/html',
            fetched_at=datetime(2026, 9, 26, tzinfo=timezone.utc), html='',
            title=f'{organisation or "Independent people"} — fictional demo',
            structured_data=[{'@context': 'https://schema.org', '@graph': records}],
        ))
    return pages


def demo_rows(dataset=DEMO_DATASET):
    rows = []
    for page in demo_pages(dataset):
        for person in Extractor(None).extract(page):
            record_json = json.dumps(person, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            evidence = person['evidence']
            rows.append({
                'identity_key': person['identity_key'],
                'evidence_key': sha256(record_json.encode('utf-8')).hexdigest(),
                'record_json': record_json, 'confidence': person['confidence'],
                **{key: evidence[key] for key in ('source_url', 'fetched_at', 'method', 'location')},
            })
    return rows


def seed_demo(driver, database='neo4j', dataset=DEMO_DATASET):
    """Seed only our namespace; refuse ownership collisions before any writes."""
    rows = demo_rows(dataset)

    def write(tx):
        collisions = tx.run('''
            MATCH (n)
            WHERE ((n:Person AND n.identity_key IN $person_keys)
                OR (n:PersonEvidence AND n.evidence_key IN $evidence_keys))
              AND (n.demo_dataset IS NULL OR n.demo_dataset <> $dataset)
            RETURN count(n) AS count
        ''', person_keys=[r['identity_key'] for r in rows],
            evidence_keys=[r['evidence_key'] for r in rows], dataset=dataset).single()['count']
        if collisions:
            raise CommandError('Demo IDs already exist without this demo ownership marker; nothing was changed.')
        tx.run('''
            UNWIND $rows AS row
            MERGE (p:Person {identity_key: row.identity_key})
            ON CREATE SET p.demo_dataset = $dataset
            SET p.confidence = CASE WHEN p.confidence IS NULL OR p.confidence < row.confidence
                THEN row.confidence ELSE p.confidence END
            MERGE (e:PersonEvidence {evidence_key: row.evidence_key})
            ON CREATE SET e.demo_dataset = $dataset, e.record_json = row.record_json,
                e.source_url = row.source_url, e.fetched_at = row.fetched_at,
                e.method = row.method, e.location = row.location, e.confidence = row.confidence
            MERGE (p)-[r:HAS_EVIDENCE]->(e)
            ON CREATE SET r.demo_dataset = $dataset
        ''', rows=rows, dataset=dataset).consume()
        return {'people': len(rows), 'evidence': len(rows)}

    with driver.session(database=database) as session:
        return session.execute_write(write)


def delete_demo(driver, database='neo4j', dataset=DEMO_DATASET):
    """Remove exact owned records, retaining nodes with any other relationships.

    Never uses DETACH DELETE: unrelated links and their nodes remain intact.
    If a demo evidence record was modified, leave it for manual inspection.
    """
    rows = demo_rows(dataset)

    def remove(tx):
        links = tx.run('''
            UNWIND $rows AS row
            MATCH (p:Person {identity_key: row.identity_key, demo_dataset: $dataset})
                -[r:HAS_EVIDENCE {demo_dataset: $dataset}]->
                (e:PersonEvidence {evidence_key: row.evidence_key, demo_dataset: $dataset})
            WHERE e.record_json = row.record_json
            DELETE r RETURN count(r) AS count
        ''', rows=rows, dataset=dataset).single()['count']
        evidence = tx.run('''
            UNWIND $rows AS row
            MATCH (e:PersonEvidence {evidence_key: row.evidence_key, demo_dataset: $dataset})
            WHERE e.record_json = row.record_json AND NOT EXISTS { MATCH (e)--() }
            DELETE e RETURN count(e) AS count
        ''', rows=rows, dataset=dataset).single()['count']
        people = tx.run('''
            MATCH (p:Person {demo_dataset: $dataset})
            WHERE p.identity_key IN $keys AND NOT EXISTS { MATCH (p)--() }
            DELETE p RETURN count(p) AS count
        ''', keys=[r['identity_key'] for r in rows], dataset=dataset).single()['count']
        retained = tx.run('''
            MATCH (n) WHERE n.demo_dataset = $dataset AND
                ((n:Person AND n.identity_key IN $person_keys) OR
                 (n:PersonEvidence AND n.evidence_key IN $evidence_keys))
            RETURN count(n) AS count
        ''', person_keys=[r['identity_key'] for r in rows],
            evidence_keys=[r['evidence_key'] for r in rows], dataset=dataset).single()['count']
        return {'people_deleted': people, 'evidence_deleted': evidence,
                'links_deleted': links, 'nodes_retained': retained}

    with driver.session(database=database) as session:
        return session.execute_write(remove)


def refresh_demo(driver, database='neo4j', dataset=DEMO_DATASET):
    """Fully wipe and reseed this demo dataset, ignoring delete_demo's
    conservative retention. All demo data is fictional and disposable, so this
    also removes enrichment-added findings (skills, risk factors, etc.) and
    demo enrichment/profile jobs, which delete_demo intentionally never touches.
    """
    def wipe(tx):
        dataset_nodes = tx.run(
            'MATCH (n) WHERE n.demo_dataset = $dataset DETACH DELETE n RETURN count(n) AS count',
            dataset=dataset).single()['count']
        enrichment_evidence = tx.run(
            "MATCH (n:PersonEvidence) WHERE n.enrichment_namespace = 'demo' DETACH DELETE n RETURN count(n) AS count"
        ).single()['count']
        jobs = tx.run(
            "MATCH (j:EnrichmentJob) WHERE j.namespace = 'demo' DETACH DELETE j RETURN count(j) AS count"
        ).single()['count']
        orphans = tx.run(
            'MATCH (p:Person) WHERE NOT EXISTS { MATCH (p)--() } DELETE p RETURN count(p) AS count'
        ).single()['count']
        return dict(dataset_nodes_deleted=dataset_nodes, enrichment_evidence_deleted=enrichment_evidence,
                    jobs_deleted=jobs, orphans_deleted=orphans)

    with driver.session(database=database) as session:
        cleanup = session.execute_write(wipe)
    return {**cleanup, **seed_demo(driver, database, dataset)}


@cli_entrypoint('Demo', hint='Check Neo4j settings and service availability. The current demo transaction was not confirmed.')
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--delete', action='store_true', help='Remove only owned demo records; preserve all unrelated data.')
    group.add_argument('--refresh', action='store_true', help='Delete ALL demo data (including enrichment findings and demo jobs) and reseed from scratch.')
    args = parser.parse_args(argv)
    with connected_extractor() as extractor:
        if args.delete:
            result = delete_demo(extractor.driver, extractor.database)
            print(f"Deleted {result['people_deleted']} demo people and {result['evidence_deleted']} demo evidence records.")
            if result['nodes_retained']:
                print(f"Kept {result['nodes_retained']} nodes with additional links or changed data.")
        elif args.refresh:
            result = refresh_demo(extractor.driver, extractor.database)
            print(f"Refreshed: removed {result['dataset_nodes_deleted']} base demo nodes, "
                  f"{result['enrichment_evidence_deleted']} enrichment evidence records and {result['jobs_deleted']} demo jobs. "
                  f"Reseeded {result['people']} fictional people.")
            print('Run `.venv/bin/python app/enrich.py --demo` next to repopulate skills, qualifications and other enrichment findings.')
        else:
            result = seed_demo(extractor.driver, extractor.database)
            print(f"Demo ready: {result['people']} fictional people. Re-running does not duplicate them.")
        print('Refresh the People map to see the result.')


if __name__ == '__main__':
    raise SystemExit(main())
