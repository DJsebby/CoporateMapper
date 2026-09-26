"""Connect the extractor to Neo4j using environment variables.

Run ``python database.py`` to check authentication and database access.
The context manager closes the driver after the extractor is finished.
"""

from contextlib import contextmanager
import os

from neo4j import GraphDatabase

from extractor import Extractor


@contextmanager
def connected_extractor():
    """Yield an Extractor backed by a verified, caller-configured database."""
    password = os.environ.get('NEO4J_PASSWORD')
    if not password:
        raise ValueError('Set NEO4J_PASSWORD before connecting to Neo4j.')
    uri = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    username = os.environ.get('NEO4J_USERNAME', 'neo4j')
    database = os.environ.get('NEO4J_DATABASE', 'neo4j')
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            session.run('RETURN 1 AS connected').consume()
        yield Extractor(driver, database=database)


if __name__ == '__main__':
    with connected_extractor():
        print('Neo4j connection verified; extractor is ready.')
