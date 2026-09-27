"""Run the shared enrichment worker on selected people or the built-in demo.

Run with the API stopped (one worker process). --demo always takes its inputs
from demo.py; it cannot relabel a database person or arbitrary file as fictional.
"""
import argparse
import json
from uuid import uuid4

from cli_support import CommandError, cli_entrypoint


@cli_entrypoint('Enrichment', hint='Check Neo4j and run only one API/enrichment process. Earlier findings remain saved.')
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--demo', action='store_true', help='Use the 23 built-in fictional demo people and offline source responses.')
    inputs.add_argument('--person-id', action='append', help='Existing employee identity key; repeat for up to 20 people.')
    parser.add_argument('--search-again', action='store_true', help='Bypass the seven-day search cache; consumes one additional attempt per confirmed employee.')
    args = parser.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv()
    from api import Neo4jPeopleStore, aggregate_people
    from database import connected_extractor
    from enrichment import EnrichmentEngine, WorkerLock, job_public
    from enrichment_store import EnrichmentError, Neo4jEnrichmentStore
    from enrichment_sources import LiveSources
    lock = WorkerLock()
    try:
        lock.acquire()
    except RuntimeError as exc:
        raise CommandError(str(exc)) from None
    try:
        with connected_extractor() as extractor:
            if args.demo:
                from demo import seed_demo
                from enrichment_demo import DemoSources
                seed_demo(extractor.driver, extractor.database)
                sources = DemoSources()
                person_ids = [record['identity_key'] for record in sources.seeds()]
            else:
                sources = LiveSources()
                person_ids = args.person_id
            people_store = Neo4jPeopleStore(extractor.driver, extractor.database)
            store = Neo4jEnrichmentStore(extractor.driver, extractor.database, namespace='demo' if args.demo else 'real')
            worker = EnrichmentEngine(store, lambda identity: aggregate_people(people_store.read(identity)),
                                      sources, allowance=1000000 if args.demo else None)
            store.interrupt_unfinished()
            try:
                # The demo fixture count is not user-controlled and may exceed one
                # job's 20-person cap; --person-id keeps the existing single-job
                # limit, since that cap is a deliberate per-run control for real employees.
                batches = [person_ids[i:i + 20] for i in range(0, len(person_ids), 20)] if args.demo else [person_ids]
                results = []
                for batch in batches:
                    try:
                        job = worker.create(batch, uuid4().hex, args.search_again)
                    except EnrichmentError as exc:
                        raise CommandError(str(exc)) from None
                    result = worker.run(job['id'])
                    results.append(result)
                    print(json.dumps(job_public(result), indent=2))
                print('Results are saved. Start the local API and open http://127.0.0.1:8000 to inspect findings and pending reviews.')
                return 0 if all(result['status'] in {'completed', 'awaiting_review'} for result in results) else 2
            finally:
                sources.close()
    finally:
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
