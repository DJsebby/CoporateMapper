"""Connect the extractor to Neo4j using environment variables.

Run ``python app/database.py`` to check authentication and database access.
The context manager closes the driver after the extractor is finished.
"""

from contextlib import contextmanager
import os

from extractor import Extractor
from cli_support import CommandError, cli_entrypoint


@contextmanager
def connected_extractor():
    """Yield an Extractor backed by a verified, caller-configured database."""
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise CommandError('Set NEO4J_PASSWORD before connecting to Neo4j (load .env into your shell).')
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    username = os.environ.get('NEO4J_USERNAME', 'neo4j')
    database = os.environ.get('NEO4J_DATABASE', 'neo4j')
    from neo4j import GraphDatabase

    with GraphDatabase.driver(
        uri, auth=(username, password), connection_timeout=10,
        connection_acquisition_timeout=15, max_transaction_retry_time=15,
    ) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            session.run('RETURN 1 AS connected').consume()
        yield Extractor(driver, database=database)


@cli_entrypoint('Database check', hint='Check that Neo4j is running and the NEO4J_* settings are correct.')
def main():
    with connected_extractor():
        print('Neo4j connection verified; extractor is ready.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
