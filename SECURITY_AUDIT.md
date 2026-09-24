# CALE Shop — Security Audit and Remediation

## Scope

Reviewed the uploaded CALE Shop Django/MySQL project source, including settings, URL routing, customer views, custom administration views, forms, models, cart/order services, image processing, templates, dependencies, and existing tests.

## Findings before remediation

| Area | Finding | Severity before fix | Status |
|---|---|---:|---|
| Secrets | `.env` was ignored, but secret/deployment file patterns were incomplete | Medium | Fixed |
| Production settings | `DEBUG` and security settings were permissive by default | High | Fixed |
| HTTPS | No production HTTPS/HSTS enforcement | High | Fixed |
| Input validation | Django forms existed, but plain-text normalization and length/content checks were incomplete | Medium | Fixed |
| SQL injection | No raw SQL was found in the reviewed source; Django ORM was used | Low | Verified |
| Output/XSS | No `|safe` or `autoescape off` was found; template auto-escaping was active | Low | Verified + CSP |
| Rate limiting | Login/registration/password reset and sensitive mutations were not throttled | High | Fixed |
| Password policy | Django validators existed but minimum length was not explicitly hardened | Medium | Fixed |
| Password hashing | Django default hashing was used, but Argon2 was not explicitly primary | Medium | Fixed |
| CAPTCHA | No anti-bot challenge was present | High | Fixed with Turnstile |
| CORS | No explicit policy existed | Medium | Fixed with empty-by-default allow-list |
| Security headers | Only Django defaults were present | High | Fixed |
| Directory listing | Application did not intentionally expose source directories, but production web-server behavior was not documented/enforced | Medium | Fixed/documented |
| Dependencies | Django dependency was unbounded within 5.x; security packages were missing | High | Fixed |
| Error handling | Production logging/error handling was not sufficiently hardened/documented | Medium | Fixed |
| Authorization | Customer ownership checks existed; custom admin had redundant decorators and one dashboard authorization gap | High | Fixed |

## Implemented controls

- `.env`, certificates, keys, logs, local DBs, and runtime files are ignored.
- Production requires an explicit `SECRET_KEY` when `DEBUG=False`.
- HTTPS redirect, Secure cookies, HSTS, proxy HTTPS support, and CSRF trusted origins are configurable through environment variables.
- `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, CSP, and Django clickjacking protection are enabled.
- CORS is empty-by-default and only allows explicitly configured origins.
- Plain-text user fields normalize Unicode, strip HTML/control characters, and enforce sensible length/content rules.
- Product and profile image uploads are verified by Pillow and converted to WebP; maximum original upload size is 10 MB.
- Oversized image uploads are rejected while being received; the Nginx example caps the complete request body at 11 MB to allow multipart overhead.
- No raw SQL APIs were found in the source reviewed.
- Login, registration, password reset, checkout, and order-status mutations are rate-limited.
- Cloudflare Turnstile is required in production for login, registration, and password-reset request forms; local DEBUG mode may operate without keys.
- Passwords use Argon2 as the primary Django password hasher with legacy hashers retained for transparent migration.
- Passwords require at least 12 characters plus upper/lower-case letters, numbers, and a special character.
- Password reset uses Django's built-in token flow and does not reveal whether an email address exists.
- Staff administration requires both `is_staff` and the specific Django permission for each operation.
- Customer order and cart queries are scoped to the authenticated user.
- Production 404/500 templates avoid stack traces and database/system details.
- Rotating Django logs are stored outside source control.
- Nginx production configuration disables directory listing and denies dotfiles.

## Dependency decision

Django was pinned to **5.2.17**, the latest 5.2 security release available at the time of this review. Django 5.2 is an LTS release, and 5.2.17 includes security fixes issued in August 2026. The project was kept on the 5.2 line rather than jumping to Django 6.x to minimize compatibility risk.

Other security-related dependencies were added or bounded: `python-dotenv`, `argon2-cffi`, `mysqlclient`, and Pillow. The exact dependency versions should still be checked with `pip-audit` in the project's normal Internet-connected development/CI environment before release.

## Verification performed in this environment

- Python AST parse: **PASS** for all project Python files.
- `py_compile` / `compileall`: **PASS**.
- Static scan for `raw()`, `extra()`, direct `cursor()` use, `csrf_exempt`, template `|safe`, and `autoescape off`: **PASS — none found**.
- Secret-file scan: **PASS — no `.env`, private key, or certificate files found in the working project**.
- Full Django test suite and `manage.py check --deploy`: **NOT EXECUTED HERE** because the execution environment did not have Django installed and could not reach PyPI to install the project's dependencies. The test suite and deployment check must be run after installing `requirements.txt` in the project's normal virtual environment.

## Required production setup

- Configure real HTTPS certificates/reverse proxy.
- Set production environment variables.
- Configure Cloudflare Turnstile site/secret keys.
- Configure SMTP for password reset.
- Configure Redis when using multiple application workers so rate-limit counters are shared.
- Run `python manage.py migrate` and `python manage.py collectstatic`.
- Run `python manage.py check --deploy` and `python manage.py test` before release.
