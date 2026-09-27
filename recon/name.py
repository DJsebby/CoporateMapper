from pathlib import Path
import sys

if __package__ in {None, ''}:
    # recon/email.py must not shadow the standard-library email package.
    script_directory = Path(__file__).resolve().parent
    sys.path[:] = [str(script_directory.parent)] + [
        entry for entry in sys.path if Path(entry).resolve() != script_directory
    ]

import http.client
import json
import os

from cli_support import CommandError


def search_person(name: str, company: str = "", role: str = "") -> dict:
	from dotenv import load_dotenv
	load_dotenv()
	api_key = os.getenv("SERPER_API_KEY", "")
	if not api_key:
		raise CommandError("Set SERPER_API_KEY in .env or the environment.")

	from enrichment_sources import build_query
	query = build_query(name, company)
	if role.strip():
		role_phrase = " ".join(role.replace(chr(34), " ").split())
		query = query.removesuffix(" Australia") + f' "{role_phrase}" Australia'
	connection = http.client.HTTPSConnection("google.serper.dev", timeout=15)
	try:
		connection.request(
			"POST",
			"/search",
			json.dumps({"q": query, "num": 10, "gl": "au"}),
			{
				"X-API-KEY": api_key,
				"Content-Type": "application/json",
			},
		)
		response = connection.getresponse()
		body = response.read().decode("utf-8")
		if response.status >= 400:
			raise CommandError(f"Serper returned HTTP {response.status}. Check your API key, quota, and service availability.")
		results = json.loads(body)
		if not isinstance(results, dict):
			raise CommandError("Serper returned an unexpected response. Try again later.")
		return results
	finally:
		connection.close()
