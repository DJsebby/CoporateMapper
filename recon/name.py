import http.client
import json
import os

from dotenv import load_dotenv


def search_person(name: str, company: str = "", role: str = "") -> dict:
	load_dotenv()
	api_key = os.getenv("SERPER_API_KEY", "")
	if not api_key:
		raise RuntimeError("Set SERPER_API_KEY in .env or the environment")

	query = " ".join(value.strip() for value in (name, company, role) if value.strip())
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
			detail = body.replace(api_key, "[redacted]")[:300]
			raise RuntimeError(f"Serper returned HTTP {response.status}: {detail}")
		return json.loads(body)
	finally:
		connection.close()
