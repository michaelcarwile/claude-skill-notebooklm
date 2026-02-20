#!/usr/bin/env python3
"""Visit each notebook URL and extract the actual title from NotebookLM."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_utils import BrowserFactory

LIBRARY_PATH = Path(__file__).parent.parent / "data" / "library.json"

def get_notebook_title(playwright, url, headless=True):
    """Open a notebook and extract its title from the page/tab title."""
    context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)  # Wait for page to fully render

        # Primary method: page title is "Notebook Title - NotebookLM"
        title = None
        page_title = page.title()
        if page_title and " - NotebookLM" in page_title:
            title = page_title.replace(" - NotebookLM", "").strip()
        elif page_title and page_title.strip() and page_title.strip() != "NotebookLM":
            title = page_title.strip()

        # Fallback: look for notebook-specific title elements (avoid chat input)
        if not title:
            for sel in ['div[class*="notebook-title"]', 'input[aria-label*="title"]']:
                try:
                    el = page.query_selector(sel)
                    if el:
                        val = el.get_attribute("value") or el.inner_text()
                        if val and val.strip() and len(val.strip()) > 2:
                            title = val.strip()
                            break
                except:
                    continue

        return title
    finally:
        context.close()


def main():
    with open(LIBRARY_PATH) as f:
        library = json.load(f)

    from patchright.sync_api import sync_playwright

    results = {}
    with sync_playwright() as playwright:
        for nb_id, nb in library["notebooks"].items():
            url = nb["url"]
            current_name = nb["name"]
            print(f"\n📓 Checking: {current_name}")
            print(f"   URL: {url}")

            try:
                actual_title = get_notebook_title(playwright, url)
                if actual_title:
                    results[nb_id] = {
                        "current": current_name,
                        "actual": actual_title,
                        "match": current_name == actual_title
                    }
                    if current_name != actual_title:
                        print(f"   ❌ Mismatch!")
                        print(f"      Current: {current_name}")
                        print(f"      Actual:  {actual_title}")
                    else:
                        print(f"   ✅ Match")
                else:
                    print(f"   ⚠️  Could not extract title")
                    results[nb_id] = {"current": current_name, "actual": None, "match": None}
            except Exception as e:
                print(f"   ❌ Error: {e}")
                results[nb_id] = {"current": current_name, "actual": None, "match": None, "error": str(e)}

            time.sleep(2)  # Brief pause between notebooks

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for nb_id, r in results.items():
        status = "✅" if r.get("match") else "❌" if r.get("actual") else "⚠️"
        print(f"{status} {r['current']}")
        if r.get("actual") and not r.get("match"):
            print(f"   → {r['actual']}")

    # Output as JSON for easy parsing
    print("\n---JSON---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
