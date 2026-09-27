import time

from pathlib import Path
import sys

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli_support import CommandError, cli_entrypoint


def check_emails_dynamic(filename):
    with open(filename, 'r', encoding='utf-8') as source:
        emails = [line.strip() for line in source if line.strip()][:50]
    if not emails:
        raise CommandError('The email list file is empty. Add an email before running this check.')
    from playwright.sync_api import sync_playwright

    print(f"[*] Loaded {len(emails)} emails. Launching automated browser session...")

    with sync_playwright() as p:
        # Launch browser (headless=False lets you watch it run; change to True to run invisibly)
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        failures = 0
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            print("[*] Navigating to Have I Been Pwned to establish session & pass Turnstile...")
            page.goto("https://haveibeenpwned.com/", wait_until="networkidle")

            # Brief pause to let Cloudflare background checks settle completely
            time.sleep(4)

            for idx, email in enumerate(emails, 1):
                print(f"\n[{idx}/{len(emails)}] Processing: {email}")

                try:
                    # Ensure we are on the home search page
                    if page.url != "https://haveibeenpwned.com/":
                        page.goto("https://haveibeenpwned.com/", wait_until="networkidle")
                        time.sleep(2)

                    # Locate the primary search input field on the HIBP page
                    input_selector = "input#accountSearchInput"
                    page.wait_for_selector(input_selector, timeout=10000)

                    # Clear, type email naturally, and submit search
                    page.fill(input_selector, "")
                    page.type(input_selector, email, delay=40)
                    page.press(input_selector, "Enter")

                    # Allow a few seconds for the dynamic results container to render
                    time.sleep(3)

                    # Evaluate page feedback text
                    page_text = page.inner_text("body")
                    if "Oh no — pwned!" in page_text:
                        print(f"  [!] BREACH FOUND: {email} appears in database leaks.")
                    elif "Good news — no pwnage found!" in page_text:
                        print(f"  [-] CLEAN: No recorded breaches found for {email}.")
                    else:
                        failures += 1
                        print("  [!] The service returned no recognised result; this check is inconclusive.", file=sys.stderr)

                except Exception:
                    failures += 1
                    print("  [!] This email check failed; no conclusion is available.", file=sys.stderr)

                # Enforce the strict 5-second rate limit between entries
                if idx < len(emails):
                    print("  [*] Rate-limiting: Sleeping for 5 seconds...")
                    time.sleep(5.0)

            if failures:
                raise CommandError(f"{failures} email checks failed; the run is incomplete.")
            print("\n[*] Finished processing all emails!")
        finally:
            browser.close()

@cli_entrypoint('Breach check')
def main():
    check_emails_dynamic('emails.txt')


if __name__ == '__main__':
    raise SystemExit(main())
