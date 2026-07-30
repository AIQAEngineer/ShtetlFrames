"""Route-table integrity: every serve.py route spec resolves to a callable,
hub pages exist on disk, and legacy redirects point at real hubs."""

from __future__ import annotations

import serve


def test_get_routes_resolve():
    for path, spec in serve.GET_ROUTES.items():
        func = serve.resolve_route(spec)
        assert callable(func), f"GET {path} -> {spec} is not callable"


def test_post_routes_resolve():
    for path, spec in serve.POST_ROUTES.items():
        func = serve.resolve_route(spec)
        assert callable(func), f"POST {path} -> {spec} is not callable"


def test_job_detail_handler_resolves():
    # /api/jobs/<id> is dispatched by prefix, outside GET_ROUTES.
    func = getattr(serve.load_route_module("api_jobs"), "handle_get_job", None)
    assert callable(func)


def test_pages_exist_on_disk():
    for path, filename in serve.PAGES.items():
        assert (serve.WEB_DIR / filename).is_file(), f"{path} -> missing {filename}"


def test_redirects_target_served_pages():
    served = {p for p in serve.PAGES if not p.endswith(".html")}
    for old, target in serve.PAGE_REDIRECTS.items():
        base = target.split("?", 1)[0]
        assert base in served, f"{old} -> {target}: base page not in PAGES"
        # Both /foo and /foo.html variants redirect together.
        bare = old[: -len(".html")] if old.endswith(".html") else old
        assert serve.PAGE_REDIRECTS.get(bare) == target


def test_get_hints_are_post_only_endpoints():
    for path in serve.GET_HINTS:
        # Either the path itself accepts POST, or it's a namespace hint for
        # the real endpoints beneath it (e.g. /api/clip -> /api/clip/load).
        routed = path in serve.POST_ROUTES
        namespace = any(p.startswith(path + "/") for p in serve.POST_ROUTES)
        assert routed or namespace, f"hint for {path} points at nothing"
        assert path not in serve.GET_ROUTES, f"hint for {path} shadows a GET route"
