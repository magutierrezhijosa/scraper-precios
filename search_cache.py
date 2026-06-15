"""Search Google cache for actual cached Immowelt content."""
with open(
    r'C:\Users\migue\.local\share\opencode\tool-output\tool_ecb9327590010l9UFT7cWSNuuT',
    'r', encoding='utf-8', errors='replace',
) as f:
    content = f.read()

idx = content.find('immowelt')
if idx >= 0:
    print('Found "immowelt" at offset', idx)
    print(repr(content[idx-100:idx+300]))
else:
    print('No immowelt reference found')

idx2 = content.find('cached')
if idx2 >= 0:
    print('\nFound "cached" at offset', idx2)
    print(content[idx2:idx2+300])
