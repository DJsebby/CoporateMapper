import json

from recon.name import search_person


def main() -> None:
	results = search_person('"Steven Brugioni"', company="bmw")
	print(json.dumps(results, indent=2))


if __name__ == "__main__":
	main()
