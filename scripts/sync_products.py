"""
TequilaLiquorStore.com — Daily Feed to Matrixify CSV
-----------------------------------------------------
Downloads the partner feed, filters tequila-only products,
and outputs a Matrixify-ready CSV for daily scheduled import.

- Products in both old and new feed: UPDATED (price, image, availability)
- Products only in new feed: CREATED as new products
- Products only in old feed: set to Published=FALSE (hidden, not deleted)

Environment variables required (set as GitHub Secrets):
  FEED_URL   https://www.liquorstore-online.com/gmcfeed/shopify_feed_tls.csv

Output: output/matrixify_update.csv
"""

import csv
import io
import os
import urllib.request

# ── Config ─────────────────────────────────────────────────────────────────────
FEED_URL         = os.environ.get('FEED_URL', 'https://www.liquorstore-online.com/gmcfeed/shopify_feed_tls.csv')
TEQUILA_CATEGORY = 'Tequila'
OUTPUT_FILE      = 'output/matrixify_update.csv'
EXISTING_FILE    = 'output/matrixify_update.csv'

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)

def download_feed(url):
    log(f"Downloading feed from {url}...")
    with urllib.request.urlopen(url) as resp:
        content = resp.read().decode('utf-8-sig')
    log(f"  Downloaded {len(content):,} bytes")
    return content

def parse_new_feed(content):
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    log(f"  Total products in feed: {len(rows):,}")
    return rows

def load_existing_handles():
    handles = set()
    try:
        with open(EXISTING_FILE, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                handles.add(row['Handle'])
        log(f"  Existing products in Shopify: {len(handles):,}")
    except FileNotFoundError:
        log("  No existing file found, starting fresh")
    return handles

def filter_tequila(rows):
    tequilas = [r for r in rows if TEQUILA_CATEGORY in r.get('Product category', '')]
    log(f"  Tequila products: {len(tequilas):,}")
    return tequilas

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

def get_published(status):
    return 'TRUE' if status.lower() == 'active' else 'FALSE'

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("TequilaLiquorStore.com — Daily Feed Converter")
    log("=" * 60)

    # Load existing handles from current CSV
    existing_handles = load_existing_handles()

    # Download and filter new feed
    content = download_feed(FEED_URL)
    rows = parse_new_feed(content)
    tequilas = filter_tequila(rows)

    # Track which handles appear in new feed
    new_handles = set()
    output_rows = []
    updated = 0
    created = 0

    for row in tequilas:
        title = row.get('Title', '').strip()
        if not title:
            continue

        handle = row.get('URL handle', '').strip()
        if not handle:
            continue

        price = row.get('Price', '').strip()
        status = row.get('Status', 'active')
        vendor = row.get('Vendor', '').strip()
        image = row.get('Product image URL', '').strip()

        new_handles.add(handle)

        if handle in existing_handles:
            updated += 1
        else:
            created += 1

        output_rows.append({
            'Handle':        handle,
            'Title':         title,
            'Type':          'Tequila',
            'Tags':          get_style_tags(title),
            'Vendor':        vendor if vendor else 'TequilaLiquorStore.com',
            'Published':     get_published(status),
            'Variant Price': price,
            'Image Src':     image,
        })

    # Products no longer in new feed — hide them instead of deleting
    discontinued = existing_handles - new_handles
    for handle in discontinued:
        output_rows.append({
            'Handle':        handle,
            'Title':         '',
            'Type':          '',
            'Tags':          '',
            'Vendor':        '',
            'Published':     'FALSE',
            'Variant Price': '',
            'Image Src':     '',
        })

    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)

    # Write CSV
    fieldnames = ['Handle', 'Title', 'Type', 'Tags', 'Vendor', 'Published', 'Variant Price', 'Image Src']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    log(f"\n✅ Done!")
    log(f"  Updated existing products: {updated}")
    log(f"  Created new products: {created}")
    log(f"  Discontinued (hidden): {len(discontinued)}")
    log(f"  Total rows written: {len(output_rows)}")
    log("Matrixify will pick this up on its daily schedule.")

if __name__ == '__main__':
    main()
