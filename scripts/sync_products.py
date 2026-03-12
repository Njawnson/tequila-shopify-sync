"""
TequilaLiquorStore.com — Daily Product Sync
--------------------------------------------
Downloads the Google Shopping feed, filters tequila products,
and updates prices + availability in Shopify via the Admin API.

Environment variables required (set as GitHub Secrets):
  SHOPIFY_STORE_HANDLE   e.g. sendliquorgifts-com-1156
  SHOPIFY_ACCESS_TOKEN   from Shopify Admin → Settings → Apps → Develop apps
  FEED_URL               https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt
"""

import csv
import io
import os
import sys
import time
import json
import urllib.request
import urllib.error
from collections import defaultdict

# ── Config ─────────────────────────────────────────────────────────────────────
FEED_URL            = os.environ.get('FEED_URL', 'https://www.tequilaliquorstore.com/gmcfeed/google_feed.txt')
SHOPIFY_STORE       = os.environ.get('SHOPIFY_STORE_HANDLE', '')
SHOPIFY_TOKEN       = os.environ.get('SHOPIFY_ACCESS_TOKEN', '')
SHOPIFY_API_VERSION = '2024-01'
TEQUILA_CATEGORY    = 'Tequila'
BATCH_SIZE          = 10   # products per batch
SLEEP_BETWEEN_CALLS = 0.5  # seconds between API calls

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg):
    print(msg, flush=True)

def shopify_request(method, endpoint, payload=None):
    url = f"https://{SHOPIFY_STORE}.myshopify.com/admin/api/{SHOPIFY_API_VERSION}/{endpoint}"
    data = json.dumps(payload).encode('utf-8') if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            'X-Shopify-Access-Token': SHOPIFY_TOKEN,
            'Content-Type': 'application/json',
        },
        method=method
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        log(f"  HTTP {e.code}: {body[:200]}")
        return None

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
    log(f"  Tequila products found: {len(tequilas):,}")
    return tequilas

def parse_price(price_str):
    try:
        return float(price_str.replace(' USD', '').strip())
    except:
        return None

def make_handle(title):
    handle = title.lower()
    for ch in ['/', '\\', ' ', '"', "'", ',', '.', '(', ')', '&', '%', '#']:
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

# ── Shopify sync ───────────────────────────────────────────────────────────────

def get_all_shopify_products():
    """Fetch all products from Shopify, paginated."""
    log("Fetching existing Shopify products...")
    products = {}
    url = f"products.json?limit=250&fields=id,handle,variants,tags,product_type"

    while url:
        resp = shopify_request('GET', url)
        if not resp:
            break
        for p in resp.get('products', []):
            products[p['handle']] = p
        # Check for next page via Link header — simplified: just paginate by since_id
        batch = resp.get('products', [])
        if len(batch) < 250:
            break
        last_id = batch[-1]['id']
        url = f"products.json?limit=250&fields=id,handle,variants,tags,product_type&since_id={last_id}"

    log(f"  Found {len(products):,} products in Shopify")
    return products

def sync_product(shopify_product, feed_row):
    """Update price and availability for a single product."""
    product_id = shopify_product['id']
    feed_price = parse_price(feed_row.get('price', ''))
    feed_availability = feed_row.get('availability', 'in stock').lower()
    is_available = 'in stock' in feed_availability

    updates = {}

    # Update variant price
    if feed_price and shopify_product.get('variants'):
        variant = shopify_product['variants'][0]
        current_price = float(variant.get('price', 0))
        if abs(current_price - feed_price) > 0.01:
            updates['variants'] = [{'id': variant['id'], 'price': f"{feed_price:.2f}"}]

    # Update published status based on availability
    current_status = shopify_product.get('status', 'active')
    new_status = 'active' if is_available else 'draft'
    if current_status != new_status:
        updates['status'] = new_status

    if updates:
        updates['id'] = product_id
        result = shopify_request('PUT', f"products/{product_id}.json", {'product': updates})
        return result is not None
    return False  # No update needed

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not SHOPIFY_STORE or not SHOPIFY_TOKEN:
        log("ERROR: Set SHOPIFY_STORE_HANDLE and SHOPIFY_ACCESS_TOKEN environment variables.")
        sys.exit(1)

    log("=" * 60)
    log("TequilaLiquorStore.com — Daily Product Sync")
    log("=" * 60)

    # 1. Download and parse feed
    content = download_feed(FEED_URL)
    rows = parse_feed(content)
    tequilas = filter_tequila(rows)

    # Build feed lookup by handle
    feed_by_handle = {}
    for row in tequilas:
        handle = make_handle(row['title'])
        feed_by_handle[handle] = row

    # 2. Get Shopify products
    shopify_products = get_all_shopify_products()

    # 3. Sync
    log("\nSyncing products...")
    updated = 0
    skipped = 0
    not_found = 0

    for handle, feed_row in feed_by_handle.items():
        if handle in shopify_products:
            was_updated = sync_product(shopify_products[handle], feed_row)
            if was_updated:
                updated += 1
                log(f"  ✓ Updated: {feed_row['title'][:60]}")
            else:
                skipped += 1
        else:
            not_found += 1

        time.sleep(SLEEP_BETWEEN_CALLS)

    log("\n" + "=" * 60)
    log(f"Sync complete!")
    log(f"  Updated:   {updated:>4} products")
    log(f"  Unchanged: {skipped:>4} products")
    log(f"  Not found: {not_found:>4} products (may need initial import)")
    log("=" * 60)

if __name__ == '__main__':
    main()

