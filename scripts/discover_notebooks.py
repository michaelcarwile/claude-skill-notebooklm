#!/usr/bin/env python3
"""Discover all notebooks from the NotebookLM home page."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from browser_utils import BrowserFactory

LIBRARY_PATH = Path(__file__).parent.parent / "data" / "library.json"
NOTEBOOKLM_HOME = "https://notebooklm.google.com/"


def discover_notebooks(playwright, headless=True):
    """Visit NotebookLM home page and extract all notebook URLs and titles."""
    context = BrowserFactory.launch_persistent_context(playwright, headless=headless)
    try:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(NOTEBOOKLM_HOME, wait_until="domcontentloaded", timeout=60000)

        # Wait for Angular SPA to hydrate — look for project-table rows
        row_count = 0
        for attempt in range(4):
            time.sleep(5)
            row_count = page.evaluate("""() => {
                return document.querySelectorAll('project-table tr td, table tr td').length;
            }""")
            if row_count > 0:
                break
            print(f"  ⏳ Attempt {attempt + 1}: waiting for table to render...")

        if row_count == 0:
            return []

        # Extract titles and metadata from table rows first
        row_data = page.evaluate("""() => {
            const results = [];
            const rows = document.querySelectorAll('project-table tr, table tr');
            for (const row of rows) {
                const cells = row.querySelectorAll('td');
                if (cells.length === 0) continue;
                const cellTexts = Array.from(cells).map(td => td.textContent.trim());
                let title = '';
                for (const text of cellTexts) {
                    if (text && text.length > 1 && !text.match(/^(\\d+|\\.\\.\\.)$/)) {
                        title = text;
                        break;
                    }
                }
                if (title) results.push({ title: title, cellTexts: cellTexts });
            }
            return results;
        }""")

        print(f"  Found {len(row_data)} notebooks in table. Resolving URLs...")

        # Click each row to navigate, capture URL, then return to home page
        notebooks = []
        for i, rd in enumerate(row_data):
            title = rd["title"]
            sources = rd["cellTexts"][1] if len(rd["cellTexts"]) > 1 else ""
            date = rd["cellTexts"][2] if len(rd["cellTexts"]) > 2 else ""

            try:
                # Find the matching row by title text and click it
                clicked = page.evaluate("""(title) => {
                    const cells = document.querySelectorAll('project-table tr td:first-child, table tr td:first-child');
                    for (const cell of cells) {
                        if (cell.textContent.trim() === title) {
                            cell.click();
                            return true;
                        }
                    }
                    return false;
                }""", title)

                if clicked:
                    page.wait_for_url("**/notebook/**", timeout=15000)
                    url = page.url
                    print(f"  {i+1}/{len(row_data)}. {title}")
                    print(f"           → {url}")
                    notebooks.append({"title": title, "url": url, "sources": sources, "date": date})
                else:
                    print(f"  {i+1}/{len(row_data)}. {title} → ⚠️ Row not found")
                    notebooks.append({"title": title, "url": None, "sources": sources, "date": date})
            except Exception as e:
                print(f"  {i+1}/{len(row_data)}. {title} → ❌ {e}")
                notebooks.append({"title": title, "url": None, "sources": sources, "date": date})

            # Navigate back to home page fresh each time
            page.goto(NOTEBOOKLM_HOME, wait_until="domcontentloaded", timeout=60000)
            # Wait for table to fully re-render with all rows
            for wait_attempt in range(10):
                time.sleep(3)
                current_rows = page.evaluate("""() => {
                    const cells = document.querySelectorAll('project-table tr td:first-child, table tr td:first-child');
                    return Array.from(cells).map(c => c.textContent.trim()).filter(t => t.length > 0).length;
                }""")
                if current_rows >= len(row_data):
                    break

        return notebooks
    finally:
        context.close()


def main():
    show_browser = "--show-browser" in sys.argv
    sync = "--sync" in sys.argv

    from patchright.sync_api import sync_playwright

    print("🔍 Discovering notebooks from NotebookLM home page...\n")

    with sync_playwright() as playwright:
        notebooks = discover_notebooks(playwright, headless=not show_browser)

    if not notebooks:
        print("❌ No notebooks found. Try with --show-browser to debug.")
        return

    print(f"Found {len(notebooks)} notebook(s):\n")
    for i, nb in enumerate(notebooks, 1):
        print(f"  {i}. {nb['title']}")
        print(f"     {nb['url']}")

    # Load existing library
    if LIBRARY_PATH.exists():
        with open(LIBRARY_PATH) as f:
            library = json.load(f)
    else:
        library = {"notebooks": {}, "active_notebook_id": None, "updated_at": None}

    existing_urls = {nb["url"] for nb in library["notebooks"].values()}

    new_notebooks = [nb for nb in notebooks if nb["url"] not in existing_urls]

    if new_notebooks:
        print(f"\n📋 {len(new_notebooks)} NEW notebook(s) not in library:")
        for nb in new_notebooks:
            print(f"  • {nb['title']} — {nb['url']}")

        if sync:
            print("\n⏳ Adding new notebooks to library...")
            from datetime import datetime
            for nb in new_notebooks:
                slug = nb["title"].lower().strip()
                slug = slug.replace(" ", "-").replace("&", "&")
                # Remove consecutive dashes
                while "--" in slug:
                    slug = slug.replace("--", "-")
                slug = slug.strip("-")

                library["notebooks"][slug] = {
                    "id": slug,
                    "url": nb["url"],
                    "name": nb["title"],
                    "description": "",
                    "topics": [],
                    "content_types": [],
                    "use_cases": [],
                    "tags": [],
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "use_count": 0,
                    "last_used": None
                }
                print(f"  ✅ Added: {nb['title']}")

            library["updated_at"] = datetime.now().isoformat()
            with open(LIBRARY_PATH, "w") as f:
                json.dump(library, f, indent=2)
            print(f"\n💾 Library saved with {len(library['notebooks'])} total notebooks.")
            print("   ⚠️  New notebooks have empty descriptions — use Smart Add to enrich them.")
        else:
            print("\n   Run with --sync to auto-add them to your library.")
    else:
        print("\n✅ All discovered notebooks are already in your library.")

    # Output JSON for programmatic use
    print("\n---JSON---")
    print(json.dumps(notebooks, indent=2))


if __name__ == "__main__":
    main()
