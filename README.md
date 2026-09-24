# CALE Shop

Django + MySQL e-commerce application for CALE Shop, with customer accounts, cart, checkout, orders, customer profile management, and a custom role-based administration panel.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and configure the database and development settings. Never commit `.env`.
4. Create the MySQL/MariaDB database:

   ```sql
   CREATE DATABASE cale_shop CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

5. Run migrations and checks:

   ```bash
   python manage.py migrate
   python manage.py check
   python manage.py test
   ```

6. Configure administration roles if required:

   ```bash
   python manage.py setup_roles
   ```

7. Start local development:

   ```bash
   python manage.py runserver
   ```

## Production security

Before deployment, read `SECURITY.md` and `SECURITY_AUDIT.md`.

At minimum configure:

- `DEBUG=False`
- a long random `SECRET_KEY`
- exact `ALLOWED_HOSTS`
- HTTPS and HSTS
- `CSRF_TRUSTED_ORIGINS`
- Cloudflare Turnstile keys
- SMTP credentials for password reset
- a shared Redis cache when running multiple workers
- a production WSGI/ASGI server

Run:

```bash
python manage.py check --deploy
python manage.py collectstatic
```

Do not use `runserver` in production.

## Administration

- Custom admin: `/admin-panel/`
- Django admin fallback: `/django-admin/`

Access is controlled by `is_staff` plus the specific Django permission required by each operation.

## Security architecture

- Django ORM is used instead of raw SQL.
- Django CSRF protection is enabled.
- User input is normalized and validated through forms.
- Templates use Django auto-escaping; no reviewed template uses `|safe` or `autoescape off`.
- Argon2 is the primary password hasher.
- Login, registration, password reset, checkout, and order-status mutations are rate-limited.
- Cloudflare Turnstile protects sensitive authentication forms in production.
- Security headers and CSP are enabled.
- Uploaded images are verified, resized, and converted to WebP.
- Production logs are rotated and do not intentionally contain passwords or secrets.
