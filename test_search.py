import json

from recon.generic import search


def main() -> None:
	results = search('Steve.Brugioni@adelaidebmw.com.au')
	print(json.dumps(results, indent=2))


if __name__ == "__main__":
	main()
