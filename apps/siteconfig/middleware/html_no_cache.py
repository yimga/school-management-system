"""
Prevent shared/CDN/browser caching of authenticated HTML shells.

Dynamic HTML must always revalidate so post-deploy template + {% static %} hash
changes reach the browser on the next navigation.
"""


class HtmlNoCacheMiddleware:
    """Set no-store on HTML responses (200/503 maintenance pages included)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code not in (200, 503):
            return response
        content_type = (response.get("Content-Type") or "").lower()
        if "text/html" not in content_type:
            return response
        if "Cache-Control" in response:
            return response
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response
