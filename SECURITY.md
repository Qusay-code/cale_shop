# CALE Shop Security Deployment Guide

## Production requirements

1. Copy `.env.example` to `.env` only for local development, or provide the same variables through the production secret manager.
2. Set `DEBUG=False`.
3. Set a long random `SECRET_KEY` outside source control.
4. Set `ALLOWED_HOSTS` to the real hostnames only.
5. Set `SECURE_SSL_REDIRECT=True` and configure HSTS.
6. Configure `TRUST_PROXY_SSL_HEADER=True` when HTTPS terminates at a trusted reverse proxy such as Nginx.
7. Configure `CSRF_TRUSTED_ORIGINS` with the exact HTTPS origins used by the site.
8. Configure Cloudflare Turnstile keys for login, registration, and password reset.
9. Configure SMTP variables for password-reset email.
10. Configure `REDIS_URL` when more than one application worker/process is used so rate-limit counters are shared.
11. Run `python manage.py collectstatic` and serve `staticfiles/` from the web server.
12. Run the application behind a production WSGI/ASGI server; do not use `runserver` in production.
13. Keep `media/` outside the source repository and disable directory listing at the web server.
14. Run `python manage.py check --deploy` before every production release.

## CAPTCHA

The project uses Cloudflare Turnstile. During `DEBUG=True` development, CAPTCHA is not required when keys are empty. In production, missing CAPTCHA configuration causes sensitive forms to fail closed.

## CORS

The application currently has no public cross-origin API. Therefore the default CORS allow-list is empty. Add exact trusted origins to `CORS_ALLOWED_ORIGINS` only when a documented API integration requires them.

## Logs

Django errors are written to `logs/django.log` with rotation. The `logs/` directory is ignored by Git. Do not log passwords, CAPTCHA secrets, database passwords, or session data.

## HTTPS / Nginx

See `deployment/nginx/cale-shop.conf.example` for an example reverse-proxy configuration. TLS certificates and private keys must remain outside the repository.
