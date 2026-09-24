"""HTTP security headers for CALE Shop."""

from django.conf import settings
from django.http import HttpResponse


class CORSPolicyMiddleware:
    """Apply an explicit allow-list for cross-origin browser requests.

    CALE Shop has no public cross-origin API today, so the default allow-list
    is empty. If a future frontend/API requires CORS, origins must be added
    explicitly through ``CORS_ALLOWED_ORIGINS``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin and origin in getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if request.method == "OPTIONS" and allowed:
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
            response["Access-Control-Allow-Methods"] = ", ".join(
                getattr(settings, "CORS_ALLOWED_METHODS", [])
            )
            response["Access-Control-Allow-Headers"] = ", ".join(
                getattr(settings, "CORS_ALLOWED_HEADERS", [])
            )
            if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
                response["Access-Control-Allow-Credentials"] = "true"
        return response


class SecurityHeadersMiddleware:
    """Add browser security headers without changing application behavior."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response["Cross-Origin-Opener-Policy"] = "same-origin"
        response["Cross-Origin-Resource-Policy"] = "same-origin"

        # Django already supplies X-Frame-Options through its middleware.
        # HSTS is enabled through SECURE_HSTS_* only when production HTTPS
        # is explicitly enabled in settings.
        if not request.path.startswith("/django-admin/"):
            csp = (
                "default-src 'self'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "frame-ancestors 'none'; "
                "object-src 'none'; "
                "script-src 'self' https://challenges.cloudflare.com; "
                "style-src 'self'; "
                "img-src 'self' data: blob:; "
                "font-src 'self'; "
                "connect-src 'self' https://challenges.cloudflare.com; "
                "frame-src https://challenges.cloudflare.com;"
            )
            response["Content-Security-Policy"] = csp

        return response
