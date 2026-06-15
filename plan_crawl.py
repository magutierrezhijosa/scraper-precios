"""Analyze the crawl plan from cached national page."""
import json, re

with open(
    r'C:\Users\migue\.local\share\opencode\tool-output\tool_ecb5cb1430014726cib7Am335q',
    'r', encoding='utf-8',
) as f:
    html = f.read()

# Extract JSON
pat = re.compile(
    r'__UFRN_FETCHER__">window\[\s*"__UFRN_FETCHER__"\s*\]\s*=\s*JSON\.parse\(\s*"((?:[^"\\]|\\.)*)"\s*\)'
)
m = pat.search(html)
raw = m.group(1)
json_str = raw.encode('utf-8').decode('unicode_escape')
data = json.loads(json_str)

inner = data['data']['/immobilienpreise/deutschland']
boxes = inner.get('placeLinkBoxes', [])

states = []
cities_national = []
for box in boxes:
    for link in box.get('links', []):
        if link.get('placeType') == 'region':
            states.append(link)
        elif link.get('placeType') == 'city':
            cities_national.append(link)

print(f'States from national page: {len(states)}')
for s in states:
    print(f'  {s["placeName"]:25s} -> {s["url"]}')

print(f'\nTop cities from national page: {len(cities_national)}')
for c in cities_national:
    print(f'  {c["placeName"]:25s} -> {c["url"]}')

# Estimate total: 16 states + ~20 cities each
print(f'\nEstimate: {len(states)} states + ~{len(states)*20} cities = ~{len(states) + len(states)*20} pages (kauf only)')
print(f'With rent: ~{(len(states) + len(states)*20) * 2} pages total')
