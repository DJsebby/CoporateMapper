# Local Neo4j setup and extractor connection

This setup runs Neo4j Community locally using Docker Compose. Database files live in a persistent Docker volume; Browser and Bolt ports bind to localhost only. The Python connection uses the official Neo4j driver.

## 1. Configure credentials

Run commands from the repository root. For a fresh checkout:

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace `NEO4J_PASSWORD` with a unique password of at least eight characters. Use a shell-safe value (letters, digits, underscores, and hyphens) for the sourcing command below. If `.env` already exists, preserve it: the initial agent setup generated a password there. `.env` and `.venv` are ignored by Git. Do not paste your password into chat.

Defaults are `bolt://localhost:7687`, username `neo4j`, and database `neo4j`. `NEO4J_PASSWORD` initialises a new database only; editing it after initialisation does not change the stored database password. Change an existing password in Neo4j and then update `.env` to match.

## 2. Start Neo4j

```bash
docker compose up -d
docker compose logs --tail=30 neo4j
```

Wait for the server to report that it has started. Open <http://localhost:7474> in your browser. Connect to `bolt://localhost:7687`, use username `neo4j`, and copy the password from your local `.env` into the login form.

## 3. Install the Python driver and verify the connection

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
set -a
source .env
set +a
.venv/bin/python database.py
```

Expected output: `Neo4j connection verified; extractor is ready.` Compose loads `.env` automatically; Python reads exported environment variables, so source `.env` in each new terminal before running the connection helper.

## 4. Pass crawler output into the connected extractor

```python
from database import connected_extractor

# page is the PageDocument supplied by your crawler.
with connected_extractor() as extractor:
    people = extractor.process(page)
```

The helper checks connectivity and database access, injects the driver into `Extractor`, and closes it on exit. `process` stores people and their evidence. Use `extractor.extract(page)` for extraction without database writes. The repository currently provides the crawler's PageDocument model, not a running crawler pipeline.

In Neo4j Browser, inspect stored records with:

```cypher
MATCH (person:Person)-[relationship:HAS_EVIDENCE]->(evidence:PersonEvidence)
RETURN person, relationship, evidence
LIMIT 50;
```

Names and other extracted claims are retained in the evidence node's `record_json` property. Person nodes contain identity keys and maximum confidence.

## Stop and restart

```bash
docker compose stop
# Later:
docker compose start
```

`docker compose down` removes the container while retaining database data. Do not add `--volumes` unless you intend to delete the stored database.

Connection refused usually means the container is still starting or stopped; inspect its logs. An authentication error means the configured password does not match the stored password. If ports 7474 or 7687 are occupied, stop the conflicting service or change the host port mappings and corresponding connection URL.

This is a local development setup. Database uniqueness constraints for concurrent extractor writes remain outside this task.

References: [Neo4j Docker setup](https://neo4j.com/docs/operations-manual/current/docker/introduction/), [Python driver connection](https://neo4j.com/docs/python-manual/current/connect/).
