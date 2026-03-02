"""
Early middleware to block common scanner/probe paths with 404.
Reduces log noise and avoids any redirect (e.g. .git) that could leak info.
"""
import re
from django.http import HttpResponseNotFound


# Path prefixes and patterns that are known scanner targets; return 404 immediately.
_SCANNER_PATH_PREFIXES = (
    "/.git",
    "/.terraform",
    "/.env",
    "/.vite/",
    "/terraform",
    "/infra/",
    "/infrastructure/",
    "/wp-config",
    "/wp-content/debug.log",
    "/wp-admin",
    "/update/index.php",
    "/_internal/",
    "/setup/",
    "/main.yml",
    "/cloudformation",
    "/serverless.yml",
    "/secrets.tfvars",
    "/prod.tfvars",
    "/staging.tfvars",
    "/dev.tfvars",
    "/variables.tf",
    "/config.js",
    "/env.js",
    "/__env.js",
    "/app.js",
    "/bundle.js",
    "/vendor.js",
    "/stripe.js",
    "/checkout.js",
    "/payment.js",
    "/sw.js",
    "/settings.js",
)
_SCANNER_PATH_PATTERN = re.compile(
    r"^/(terraform\.tfstate|terraform\.tfvars|main\.yml|\.env\.vite)(\.json)?$",
    re.IGNORECASE,
)


class BlockScannerPathsMiddleware:
    """
    Return 404 for known scanner/probe paths before any URL resolution or redirect.
    Logs show probes for .git, terraform, wp-config, env files, etc.; this
    short-circuits them without hitting the rest of the stack.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or "").strip()
        if not path or path == "/":
            return self.get_response(request)

        path_lower = path.lower()
        for prefix in _SCANNER_PATH_PREFIXES:
            if path_lower.startswith(prefix.lower()):
                return HttpResponseNotFound()

        if _SCANNER_PATH_PATTERN.match(path):
            return HttpResponseNotFound()

        return self.get_response(request)
