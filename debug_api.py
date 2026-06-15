"""Analyze HTML for API endpoints and data structure."""
import re
import json

# Read the webfetch output that succeeded (national page)
with open(r'C:\Users\migue\.local\share\opencode\tool-output\tool_ecb5cb1430014726cib7Am335q', 'r', encoding='utf-8') as f:
    html = f.read()

print('Page length:', len(html))

# Find __UFRN_FETCHER__ content  
m = re.search(r'__UFRN_FETCHER__.*?JSON\.parse\(', html)
print('Has __UFRN_FETCHER__:', m is not None)

# Find all URLs in the page
urls = re.findall(r'https?://[^\s"\'<>]+', html)
api_urls = [u for u in urls if any(kw in u.lower() for kw in ['api', 'pric', 'graphql', 'data', 'rest'])]
print(f'\nFound {len(api_urls)} potential API URLs:')
for u in api_urls[:25]:
    print(f'  {u[:150]}')

# Also find relative URLs with API-like patterns
rel_urls = re.findall(r'["\'](/[^"\']*(?:api|graphql|rest|data)[^"\']*)["\']', html)
print(f'\nFound {len(rel_urls)} relative API URLs:')
for u in rel_urls[:15]:
    print(f'  {u[:150]}')

# Check for next.js data routes
for pattern in ['/_next', '/_data', '/__data']:
    count = html.count(pattern)
    if count:
        print(f'\n{pattern}: found {count} times')
