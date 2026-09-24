"""Security-related template context."""

from django.conf import settings


def security_context(request):
    """Expose only the public CAPTCHA site key to templates."""

    return {
        "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", ""),
    }
