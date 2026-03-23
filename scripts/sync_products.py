"""
TequilaLiquorStore.com — Daily Feed to Matrixify CSV
-----------------------------------------------------
Downloads the partner feed, filters tequila-only products,
deduplicates by normalized title with priority:
  1. Has image + has description (best)
  2. Has image, no description
  3. Has description, no image
  4. Neither (worst)
Within same priority, keeps lowest price.

Environment variables:
  FEED_URL   https://www.liquorstore-online.com/gmcfeed/shopify_feed_tls.csv

Output: output/matrixify_update.csv
"""

import csv
import io
import os
import re
import urllib.request

FEED_URL         = os.environ.get('FEED_URL', 'https://www.liquorstore-online.com/gmcfeed/shopify_feed_tls.csv')
TEQUILA_CATEGORY = 'Tequila'
OUTPUT_FILE      = 'output/matrixify_update.csv'

def log(msg):
    print(msg, flush=True)

def download_feed(url):
    log(f"Downloading feed from {url}...")
    with urllib.request.urlopen(url) as resp:
        content = resp.read().decode('utf-8-sig')
    log(f"  Downloaded {len(content):,} bytes")
    return content

def parse_feed(content):
    rows = list(csv.DictReader(io.StringIO(content)))
    log(f"  Total products in feed: {len(rows):,}")
    return rows

def filter_tequila(rows):
    tequilas = [r for r in rows if TEQUILA_CATEGORY in r.get('Product category', '')]
    log(f"  Tequila products: {len(tequilas):,}")
    return tequilas

def build_known_brands(rows):
    return sorted(set(r['Vendor'].strip() for r in rows if r.get('Vendor','').strip()), key=len, reverse=True)

def extract_brand(title, known_brands):
    if ' - ' in title:
        candidate = title.split(' - ')[0].strip()
        if len(candidate) > 1:
            return candidate
    title_lower = title.lower()
    for brand in known_brands:
        if title_lower.startswith(brand.lower()):
            return brand
    words = title.split()
    return ' '.join(words[:2]) if len(words) >= 2 else words[0] if words else 'Unknown'

def normalize_title(t):
    t = t.lower().strip()
    t = re.sub(r'\s*[-–]\s*\d+(\.\d+)?\s*(ml|cl|l|oz)\b', '', t)
    t = re.sub(r'\s+\d+(\.\d+)?\s*(ml|cl|l|oz)\b', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

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

def priority(row):
    has_image = bool(row.get('Image Src', '').strip())
    has_desc = bool(row.get('Body HTML', '').strip())
    if has_image and has_desc:
        return 0
    elif has_image:
        return 1
    elif has_desc:
        return 2
    else:
        return 3

def deduplicate(rows):
    seen = {}
    for row in rows:
        norm = normalize_title(row.get('Title', ''))
        try:
            price = float(row.get('Variant Price', '') or 9999)
        except:
            price = 9999

        if norm not in seen:
            seen[norm] = (row, price)
        else:
            existing_row, existing_price = seen[norm]
            new_priority = priority(row)
            existing_priority = priority(existing_row)

            if new_priority < existing_priority:
                seen[norm] = (row, price)
            elif new_priority == existing_priority and price < existing_price:
                seen[norm] = (row, price)

    deduped = [r for r, p in seen.values()]
    log(f"  After deduplication: {len(deduped):,} products")
    return deduped

def main():
    log("=" * 60)
    log("TequilaLiquorStore.com — Daily Feed Converter")
    log("=" * 60)

    content = download_feed(FEED_URL)
    rows = parse_feed(content)
    tequilas = filter_tequila(rows)
    known_brands = build_known_brands(tequilas)

    output_rows = []
    for row in tequilas:
        title = row.get('Title', '').strip()
        if not title:
            continue
        handle = row.get('URL handle', '').strip()
        if not handle:
            continue

        image = row.get('Product image URL', '').strip()
        if not image:
            continue
        vendor = row.get('Vendor', '').strip()
        if not vendor:
            vendor = extract_brand(title, known_brands)

        output_rows.append({
            'Handle':        handle,
            'Title':         title,
            'Body HTML':     row.get('Description', '').strip(),
            'Type':          'Tequila',
            'Tags':          get_style_tags(title),
            'Vendor':        vendor,
            'Published':     get_published(row.get('Status', 'active')),
            'Variant Price': row.get('Price', '').strip(),
            'Image Src':     image,
            'Variant SKU':   row.get('SKU', '').strip(),
        })

    output_rows = deduplicate(output_rows)

    os.makedirs('output', exist_ok=True)
    fieldnames = ['Handle','Title','Body HTML','Type','Tags','Vendor','Published','Variant Price','Image Src','Variant SKU']
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    log(f"\n✅ Done! {len(output_rows)} products written to {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
