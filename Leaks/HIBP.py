import time
from playwright.sync_api import sync_playwright

def check_emails_dynamic(filename):
    # Load emails from file (capped safely at 50 as requested)
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            emails = [line.strip() for line in f if line.strip()][:50]
    except FileNotFoundError:
        print(f"[!] Error: Could not find '{filename}'.")
        return

    if not emails:
        print("[!] The email list file is empty.")
        return

    print(f"[*] Loaded {len(emails)} emails. Launching automated browser session...")

    with sync_playwright() as p:
        # Launch browser (headless=False lets you watch it run; change to True to run invisibly)
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
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
                    print(f"  [*] Search executed. Check browser screen for status.")

            except Exception as e:
                print(f"  [!] Error checking {email}: {e}")

            # Enforce the strict 5-second rate limit between entries
            if idx < len(emails):
                print("  [*] Rate-limiting: Sleeping for 5 seconds...")
                time.sleep(5.0)

        print("\n[*] Finished processing all emails!")
        browser.close()

if __name__ == "__main__":
    EMAIL_LIST_FILE = "emails.txt"
    check_emails_dynamic(EMAIL_LIST_FILE)

#### TO DO - ADD FILE TO READ FROM EMAILS LIST
