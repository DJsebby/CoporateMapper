import os
import time

from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint

def fetch_sampled_wayback_site(domain, sample_count=2, output_dir="wayback_sampled_site"):
    import requests
    cdx_api_url = "https://web.archive.org/cdx/search/cdx"

    # Parameters for the CDX API query (sorted chronologically by default)
    params = {
        'url': f"{domain}/*",
        'output': 'json',
        'fl': 'timestamp,original,statuscode,mimetype',
        'filter': 'statuscode:200'
    }

    print(f"[*] Querying Wayback Machine index for: {domain}...")
    response = requests.get(cdx_api_url, params=params, timeout=15)
    try:
        response.raise_for_status()
        data = response.json()
    finally:
        response.close()
    if not isinstance(data, list) or any(not isinstance(row, list) for row in data):
        raise CommandError('Wayback returned an unexpected index response. Try again later.')
    if len(data) <= 1:
        print("[!] No archived records found for this domain.")
        return

    headers = data[0]
    rows = data[1:]

    print(f"[*] Total raw records found: {len(rows)}. Filtering out images...")

    # Filter out images and invalid mimetypes
    valid_rows = []
    for entry in rows:
        row_dict = dict(zip(headers, entry))
        mimetype = row_dict.get('mimetype', '')

        # Skip any mimetype that is an image
        if mimetype.startswith('image/'):
            continue

        valid_rows.append(row_dict)

    if not valid_rows:
        print("[!] No non-image records found.")
        return

    print(f"[*] Non-image records available: {len(valid_rows)}")

    # Select Oldest, Middle, and Recent snapshots
    total_valid = len(valid_rows)
    if total_valid <= (sample_count * 3):
        # If there aren't many records, just use all of them
        selected_rows = valid_rows
        print("[*] Dataset is small; downloading all available non-image snapshots.")
    else:
        oldest = valid_rows[:sample_count]

        mid_index = total_valid // 2
        half_sample = sample_count // 2
        middle = valid_rows[mid_index - half_sample : mid_index + half_sample + (sample_count % 2)]

        recent = valid_rows[-sample_count:]

        selected_rows = oldest + middle + recent
        print(f"[*] Selected {len(selected_rows)} targeted snapshots ({sample_count} oldest, {sample_count} middle, {sample_count} recent).")

    os.makedirs(output_dir, exist_ok=True)

    failures = 0
    for row_dict in selected_rows:
        timestamp = row_dict['timestamp']
        original_url = row_dict['original']

        # Construct raw file link using 'id_' to avoid archive toolbar
        archive_file_url = f"https://web.archive.org/web/{timestamp}id_/{original_url}"

        # Clean up local path destination
        relative_path = original_url.replace(f"https://{domain}", "").replace(f"http://{domain}", "")
        relative_path = relative_path.split('?')[0] # Strip query params

        if not relative_path or relative_path == "/":
            relative_path = f"/index_{timestamp}.html" # Append timestamp to avoid overwriting homepages
        else:
            # Inject timestamp into filename or directory to separate different versions
            path_parts = relative_path.rsplit('.', 1)
            if len(path_parts) == 2:
                relative_path = f"{path_parts[0]}_{timestamp}.{path_parts[1]}"
            else:
                relative_path = f"{relative_path}_{timestamp}"

        local_filepath = os.path.join(output_dir, relative_path.lstrip('/'))

        os.makedirs(os.path.dirname(local_filepath), exist_ok=True)

        try:
            print(f"[+] Downloading: {original_url} (Timestamp: {timestamp})")
            file_res = requests.get(archive_file_url, timeout=15)
            try:
                file_res.raise_for_status()
                with open(local_filepath, "wb") as f:
                    f.write(file_res.content)
            finally:
                file_res.close()
        except (requests.RequestException, OSError):
            failures += 1
            print('[-] An archived asset could not be downloaded or saved.', file=sys.stderr)

        time.sleep(1.0)

    if failures:
        raise CommandError(f"{failures} archived downloads failed. Earlier successful files have been saved.")
    print(f"\n[*] Done! Sampled files saved to folder: '{output_dir}'")

@cli_entrypoint('Wayback download')
def main():
    fetch_sampled_wayback_site('www.ahsca.org.au', sample_count=2)


if __name__ == '__main__':
    raise SystemExit(main())
