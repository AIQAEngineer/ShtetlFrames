"""Time individual resolve steps while the big scrape runs."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import efg

t0 = time.time()
html = efg._scrapfly_html("https://www.europeanfilmgateway.eu/detail/Venise/cm%3A%3A7d2fcf410b4128595762eab0fe0a81de")
print(f"detail fetch: {time.time()-t0:.1f}s len={len(html)}")

t0 = time.time()
r = efg.ina_resolve("AFE86003258")
print(f"ina_resolve: {time.time()-t0:.1f}s -> {'ok' if r else 'fail'}")
