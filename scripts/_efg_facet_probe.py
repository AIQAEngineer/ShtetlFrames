import sys
sys.path.insert(0, 'src')
import efg, re

html = efg.fetch_filtered_search_page('the', 0)
print('LEN', len(html))
print('result_count (filtered pre1950 video):', efg.parse_result_count(html))

# year facet blocks: find input value and any nearby count
for mm in re.finditer(r'value="(\d{4}-\d{4})"', html):
    span = html[mm.start():mm.start()+300]
    c = re.search(r'\(?([\d,]{2,})\)?', span)
    print('year facet:', mm.group(1), 'count~', c.group(1) if c else '?')

open('data/efg/_probe2.html', 'w', encoding='utf-8').write(html)
print('saved _probe2.html')
