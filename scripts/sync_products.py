"""
TequilaLiquorStore.com — Daily Feed to Matrixify CSV
-----------------------------------------------------
Downloads the Google Shopping feed, filters tequila-only products,
and outputs a Matrixify-ready CSV for daily scheduled import.

Environment variables required (set as GitHub Secrets):
  FEED_URL   https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt

Output: output/matrixify_update.csv (~742 rows, well within Basic plan limit)
"""

import csv
import io
import os
import sys
import urllib.request

# ── Config ─────────────────────────────────────────────────────────────────────
FEED_URL         = os.environ.get('FEED_URL', 'https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt')
TEQUILA_CATEGORY = 'Tequila'
OUTPUT_FILE      = 'output/matrixify_update.csv'

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)

def download_feed(url):
    log(f"Downloading feed from {url}...")
    with urllib.request.urlopen(url) as resp:
        content = resp.read().decode('utf-8-sig')
    log(f"  Downloaded {len(content):,} bytes")
    return content

def parse_feed(content):
    reader = csv.DictReader(io.StringIO(content), delimiter='\t')
    rows = list(reader)
    log(f"  Total products in feed: {len(rows):,}")
    return rows

def filter_tequila(rows):
    tequilas = [r for r in rows if TEQUILA_CATEGORY in r.get('google product category', '')]
    log(f"  Tequila products: {len(tequilas):,}")
    return tequilas

def make_handle(title):
    handle = title.lower()
    for ch in ['/', '\\', ' ', '"', "'", ',', '.', '(', ')', '&', '%', '#', '+']:
        handle = handle.replace(ch, '-')
    while '--' in handle:
        handle = handle.replace('--', '-')
    return handle.strip('-')[:100]

def get_style_tags(title):
    t = title.lower()
    tags = ['tequila']
    if 'mezcal' in t:
        tags.append('mezcal')
    if 'extra anejo' in t or 'extra añejo' in t:
        tags.append('extra-anejo')
    elif 'anejo' in t or 'añejo' in t:
        tags.append('anejo')
    elif 'reposado' in t:
        tags.append('reposado')
    elif any(x in t for x in ['blanco', 'silver', 'plata', 'cristalino']):
        tags.append('blanco')
    return ', '.join(tags)

def parse_price(price_str):
    try:
        return float(price_str.replace(' USD', '').replace('$', '').strip())
    except:
        return ''

def get_published(availability):
    return 'TRUE' if 'in stock' in availability.lower() else 'FALSE'

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("TequilaLiquorStore.com — Daily Feed Converter")
    log("=" * 60)

    # Download and filter
    content = download_feed(FEED_URL)
    rows = parse_feed(content)
    tequilas = filter_tequila(rows)

    # Build Matrixify rows — only update price, availability, and tags
    output_rows = []
    for row in tequilas:
        title = row.get('title', '').strip()
        if not title:
            continue

        price = parse_price(row.get('price', ''))
        availability = row.get('availability', 'in stock')
        brand = row.get('brand', '').strip()
        image = row.get('image link', '').strip()

        output_rows.append({
            'Handle':        make_handle(title),
            'Title':         title,
            'Type':          'Tequila',
            'Tags':          get_style_tags(title),
            'Vendor':        brand if brand else 'TequilaLiquorStore.com',
            'Published':     get_published(availability),
            'Variant Price': f"{price:.2f}" if price else '',
            'Image Src':     image,
        })

    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)

    # Write CSV
    fieldnames = ['Handle', 'Title', 'Type', 'Tags', 'Vendor', 'Published', 'Variant Price', 'Image Src']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    log(f"\n✅ Done! {len(output_rows)} tequila products written to {OUTPUT_FILE}")
    log("Matrixify will pick this up on its daily schedule.")

if __name__ == '__main__':
    main()
