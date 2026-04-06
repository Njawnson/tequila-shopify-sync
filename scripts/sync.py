"""
TequilaLiquorStore.com — Daily Feed Sync + Auto-Unpublish
----------------------------------------------------------
1. Downloads the partner feed
2. Filters tequila-only products
3. Outputs matrixify_update.csv (products to create/update)
4. Compares against live Shopify products via API
5. Outputs unpublish.csv (products missing from feed → Published: FALSE)

Environment variables (set as GitHub Actions secrets):
  FEED_URL              Partner feed CSV URL
  SHOPIFY_STORE         Your store handle (e.g. sendliquorgifts-com-1156)
  SHOPIFY_CLIENT_ID     Shopify app Client ID
  SHOPIFY_CLIENT_SECRET Shopify app Client Secret

Output:
  output/matrixify_update.csv   → import into Shopify via Matrixify
  output/unpublish.csv          → import into Shopify via Matrixify to unpublish missing products
"""

import csv
import io
import json
import os
import urllib.request
import urllib.parse

FEED_URL       = os.environ.get('FEED_URL', 'https://www.liquorstore-online.com/gmcfeed/shopify_feed_tls.csv')
STORE          = os.environ.get('SHOPIFY_STORE', 'sendliquorgifts-com-1156')
CLIENT_ID      = os.environ.get('SHOPIFY_CLIENT_ID', '')
CLIENT_SECRET  = os.environ.get('SHOPIFY_CLIENT_SECRET', '')
TEQUILA_CAT    = 'Tequila'
OUTPUT_DIR     = 'output'
UPDATE_FILE    = f'{OUTPUT_DIR}/matrixify_update.csv'
UNPUBLISH_FILE = f'{OUTPUT_DIR}/unpublish.csv'

def log(msg):
    print(msg, flush=True)

# ─── Feed ────────────────────────────────────────────────────────────────────

def download_feed(url):
    log(f"Downloading feed from {url}...")
    with urllib.request.urlopen(url) as resp:
        content = resp.read().decode('utf-8-sig')
    log(f"  Downloaded {len(content):,} bytes")
    return content

def parse_feed(content):
    rows = list(csv.DictReader(io.StringIO(content)))
    log(f"  Total rows in feed: {len(rows):,}")
    return rows

def filter_tequila(rows):
    out = [r for r in rows if TEQUILA_CAT in r.get('Product category', '')]
    log(f"  Tequila products: {len(out):,}")
    return out

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

def build_update_rows(tequilas):
    rows = []
    skipped = 0
    for row in tequilas:
        title = row.get('Title', '').strip()
        handle = row.get('URL handle', '').strip()
        image = row.get('Product image URL', '').strip()
        price = row.get('Price', '').strip()

        if not title or not handle or not image:
            skipped += 1
            continue

        rows.append({
            'Handle':        handle,
            'Title':         title,
            'Type':          'Tequila',
            'Tags':          get_style_tags(title),
            'Vendor':        row.get('Vendor', '').strip(),
            'Published':     'TRUE',
            'Variant Price': price,
            'Image Src':     image,
            'Variant SKU':   row.get('SKU', '').strip(),
        })

    log(f"  Skipped (missing title/handle/image): {skipped}")
    log(f"  Update rows: {len(rows):,}")
    return rows

# ─── Shopify API ──────────────────────────────────────────────────────────────

def get_access_token():
    log("Getting Shopify access token...")
    url = f"https://{STORE}.myshopify.com/admin/oauth/access_token"
    data = urllib.parse.urlencode({
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }).encode()
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            token = result.get('access_token', '')
            log(f"  Got access token: {'yes' if token else 'NO - check credentials'}")
            return token
    except Exception as e:
        log(f"  Token error: {e}")
        return None

def get_all_shopify_handles(token):
    log("Fetching all live products from Shopify...")
    handles = {}
    url = f"https://{STORE}.myshopify.com/admin/api/2024-01/products.json?limit=250&published_status=published&fields=id,handle,status"
    headers = {'X-Shopify-Access-Token': token}

    while url:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            link_header = resp.headers.get('Link', '')
            body = json.loads(resp.read())

        for p in body.get('products', []):
            handles[p['handle']] = p['id']

        # pagination
        next_url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(','):
                if 'rel="next"' in part:
                    next_url = part.strip().split(';')[0].strip('<> ')
                    break
        url = next_url

    log(f"  Live published products in Shopify: {len(handles):,}")
    return handles

# ─── Unpublish ────────────────────────────────────────────────────────────────

def build_unpublish_rows(feed_handles, shopify_handles):
    missing = {h: pid for h, pid in shopify_handles.items() if h not in feed_handles}
    log(f"  Products in Shopify but not in feed (to unpublish): {len(missing):,}")
    rows = [{'Handle': h, 'Published': 'FALSE'} for h in missing]
    return rows

# ─── Write CSV ────────────────────────────────────────────────────────────────

def write_csv(filepath, fieldnames, rows):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    log(f"  Written: {filepath} ({len(rows)} rows)")

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("TequilaLiquorStore — Daily Sync + Auto-Unpublish")
    log("=" * 60)

    # Step 1: Download and process feed
    content = download_feed(FEED_URL)
    rows = parse_feed(content)
    tequilas = filter_tequila(rows)
    update_rows = build_update_rows(tequilas)

    # Feed handles set
    feed_handles = {r['Handle'] for r in update_rows}

    # Step 2: Write update CSV
    update_fields = ['Handle', 'Title', 'Type', 'Tags', 'Vendor', 'Published', 'Variant Price', 'Image Src', 'Variant SKU']
    write_csv(UPDATE_FILE, update_fields, update_rows)

    # Step 3: Get Shopify live products and generate unpublish CSV
    if CLIENT_ID and CLIENT_SECRET:
        token = get_access_token()
        if token:
            shopify_handles = get_all_shopify_handles(token)
            unpublish_rows = build_unpublish_rows(feed_handles, shopify_handles)
            write_csv(UNPUBLISH_FILE, ['Handle', 'Published'], unpublish_rows)
        else:
            log("⚠️  Skipping unpublish step — could not get access token")
    else:
        log("⚠️  Skipping unpublish step — no Shopify credentials set")

    log(f"\n✅ Done!")
    log(f"   Products to update:    {len(update_rows)}")

if __name__ == '__main__':
    main()
