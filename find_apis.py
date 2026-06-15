"""Find API endpoints in cached HTML."""
import re

with open(
    r'C:\Users\migue\.local\share\opencode\tool-output\tool_ecb5cb1430014726cib7Am335q',
    'r', encoding='utf-8',
) as f:
    html = f.read()

# Find all API-like URLs
apis = re.findall(r'https?://[^"\'\\()\s>]+immowelt[^"\'\\()\s>]*', html)
seen = set()
for api in sorted(apis):
    if api not in seen:
        seen.add(api)
        if len(seen) > 30:
            break
        print(api)

# Also look for explicit JSON API patterns
print("\n--- API patterns ---")
for m in re.finditer(r'(/api/|/graphql|\.json|/rest/|/v\d/)[^"\'\\()\s<>&?]*', html):
    url = m.group(0)
    if url not in seen:
        seen.add(url)
        print(url)
