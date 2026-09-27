"""Manual live Serper query; importing this module never sends a request."""

import json

from cli_support import cli_entrypoint


@cli_entrypoint('Name search')
def main():
    from recon.name import search_person
    results = search_person('"Steven Brugioni"', company='bmw')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
