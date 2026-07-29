from urllib.parse import urlparse

def build_school_url(frontend_url_raw, subdomain, path="/"):
    """
    Build a school-specific URL from FRONTEND_URL.
    Falls back to http://localhost:3000 if the setting is bad.
    """
    if not frontend_url_raw or str(frontend_url_raw).strip().lower() in ("none", ""):
        frontend_url_raw = "http://localhost:3000"

    parsed = urlparse(str(frontend_url_raw).strip())
    scheme = parsed.scheme or "http"
    host   = parsed.hostname or "localhost"
    port   = f":{parsed.port}" if parsed.port else ""

    return f"{scheme}://{subdomain}.{host}{port}{path}"