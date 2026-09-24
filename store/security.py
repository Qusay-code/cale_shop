"""Security helpers used by CALE Shop.

This module intentionally contains small, dependency-light helpers for
request throttling and Cloudflare Turnstile validation. Secrets are read
from Django settings/environment and are never hard-coded here.
"""

from __future__ import annotations

import json
import logging
from functools import wraps
from urllib import parse, request as urllib_request

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse

logger = logging.getLogger("store")


class RateLimitExceeded(Exception):
    """Raised when a request exceeds its configured rate limit."""



def get_client_ip(request) -> str:
    """Return the client IP without trusting arbitrary proxy headers.

    ``REMOTE_ADDR`` is authoritative unless the deployment explicitly
    configures a trusted reverse proxy. The application does not trust
    ``X-Forwarded-For`` directly because clients can forge it.
    """

    return request.META.get("REMOTE_ADDR", "unknown")



def rate_limit(*, key_prefix: str, limit: int, period: int, methods=("POST",)):
    """Throttle requests using Django's configured cache backend.

    The counter is keyed by IP and, when supplied by the caller, an
    additional identifier such as username can be included in the prefix.
    For multiple application workers, configure a shared cache backend
    (for example Redis) in production.
    """

    allowed_methods = set(methods)

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method not in allowed_methods:
                return view_func(request, *args, **kwargs)

            identifier = get_client_ip(request)
            username = request.POST.get("username", "").strip().lower()
            suffix = f":{username}" if username else ""
            cache_key = f"security:rate:{key_prefix}:{identifier}{suffix}"

            # Use an atomic counter where the configured cache backend supports it.
            # The key expires automatically after the configured period.
            cache.add(cache_key, 0, timeout=period)
            count = cache.incr(cache_key)

            if count > limit:
                logger.warning("Rate limit exceeded for %s from %s", key_prefix, identifier)
                response = HttpResponse(
                    "تم تجاوز عدد المحاولات المسموح بها. يرجى المحاولة لاحقًا.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
                response["Retry-After"] = str(period)
                return response

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator



def turnstile_enabled() -> bool:
    """Return whether Turnstile is required for the current deployment."""

    return bool(
        getattr(settings, "TURNSTILE_SITE_KEY", "")
        and getattr(settings, "TURNSTILE_SECRET_KEY", "")
    )



def validate_turnstile(token: str, remote_ip: str | None = None) -> None:
    """Validate a Cloudflare Turnstile response token.

    In production, missing Turnstile configuration is treated as a
    configuration error rather than silently disabling the protection.
    During local DEBUG development the CAPTCHA may remain disabled.
    """

    site_key = getattr(settings, "TURNSTILE_SITE_KEY", "")
    secret_key = getattr(settings, "TURNSTILE_SECRET_KEY", "")

    if not site_key or not secret_key:
        if settings.DEBUG:
            return
        raise ValidationError("CAPTCHA غير مهيأ على الخادم.")

    if not token:
        raise ValidationError("يرجى إكمال اختبار CAPTCHA.")

    payload = parse.urlencode(
        {
            "secret": secret_key,
            "response": token,
            **({"remoteip": remote_ip} if remote_ip else {}),
        }
    ).encode("utf-8")

    try:
        req = urllib_request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if settings.DEBUG:
            raise ValidationError("تعذر التحقق من CAPTCHA.") from exc
        raise ValidationError("تعذر التحقق من CAPTCHA. حاول لاحقًا.") from exc

    if not result.get("success"):
        raise ValidationError("فشل التحقق من CAPTCHA.")


class SensitiveActionPermissionMixin:
    """Placeholder mixin documenting sensitive-action requirements."""

    pass
