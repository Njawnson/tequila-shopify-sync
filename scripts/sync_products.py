"""
TequilaLiquorStore.com — Daily Feed Converter
----------------------------------------------
Downloads the Google Shopping feed, converts all products
to a Matrixify-compatible CSV, and commits it back to the repo.

Matrixify then imports from the raw GitHub URL on a daily schedule.

Environment variables (set as GitHub Secrets):
  FEED_URL   https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt
"""

import csv
import io
import os
import urllib.request

FEED_URL    = os.environ.get('FEED_URL', 'https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt')
OUTPUT_FILE = 'output/matrixify_update.csv'

def log(msg):
    print(msg, flush=True)

def download_feed(url):
    log(f"Downloading feed from {url}...")
    with urllib.request.urlopen(url) as resp:
        content = resp.read().decode('utf-8-sig')
    log(f"  Downloaded {len(content):,} bytes")
    return content

def make_handle(title):
    handle = title.lower()
    for ch in ['/', '\\', ' ', '"', "'", ',', '.', '(', ')', '&', '%', '#']:
        handle = handle.replace(ch, '-')
    while '--' in handle:
        handle = handle.replace('--', '-')
    return handle.strip('-')[:100]

def get_tags(row):
    tags = []
    title = row['title'].lower()
    category = row.get('google product category', '')
    if 'Tequila' in category:
        tags.append('tequila')
        if 'extra anejo' in title or 'extra anejo' in title:
            tags.append('extra-anejo')
        elif 'anejo' in title or 'anejo' in title:
            tags.append('anejo')
        elif 'reposado' in title:
            tags.append('reposado')
        elif any(x in title for x in ['blanco', 'silver', 'plata', 'cristalino']):
            tags.append('blanco')
        if 'mezcal' in title:
            tags.append('mezcal')
    return ', '.join(tags)

def get_type(row):
    category = row.get('google product category', '')
    if 'Tequila' in category: return 'Tequila'
    elif 'Whiskey' in category or 'Scotch' in category: return 'Whiskey'
    elif 'Bourbon' in category: return 'Bourbon'
    elif 'Wine' in category: return 'Wine'
    elif 'Rum' in category: return 'Rum'
    elif 'Vodka' in category: return 'Vodka'
    elif 'Gin' in category: return 'Gin'
    elif 'Brandy' in category: return 'Brandy'
    elif 'Liqueur' in category: return 'Liqueur'
    else: return 'Spirits'

def parse_price(price_str):
    try:
        return f"{float(price_str.replace(' USD', '').strip()):.2f}"
    except:
        return ''

def get_availability(row):
    avail = row.get('availability', 'in stock').lower()
    return 'TRUE' if 'in stock' in avail else 'FALSE'

def get_vendor(row):
    brand = row.get('brand', '').strip()
    if not brand and ' - ' in row['title']:
        brand = row['title'].split(' - ')[0].strip()
    return brand

def main():
    content = download_feed(FEED_URL)
    reader = csv.DictReader(io.StringIO(content), delimiter='\t')
    rows = list(reader)
    log(f"  Total products in feed: {len(rows):,}")

    results = []
    for row in rows:
        price = parse_price(row.get('price', ''))
        if not price:
            continue
        results.append({
            'Handle':        make_handle(row['title']),
            'Title':         row['title'],
            'Type':          get_type(row),
            'Tags':          get_tags(row),
            'Vendor':        get_vendor(row),
            'Published':     get_availability(row),
            'Variant Price': price,
            'Image Src':     row.get('image link', ''),
        })

    os.makedirs('output', exist_ok=True)
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['Handle','Title','Type','Tags','Vendor','Published','Variant Price','Image Src'])
        writer.writeheader()
        writer.writerows(results)

    log(f"Done! {len(results):,} products written to {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
