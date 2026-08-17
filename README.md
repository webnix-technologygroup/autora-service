<div align="center">
  <img src="./service/static/service/logo-mark.svg" width="92" alt="AUTORA logo">

  # AUTORA

  **A complete automotive-service workflow — from online booking to workshop delivery.**

  Customer cabinet · Staff operations · Estimates · In-app updates · Django Admin

  <br>

  [![Live](https://img.shields.io/badge/LIVE_DEMO-315EFB?style=for-the-badge&logo=render&logoColor=white)](https://autora-service.onrender.com/)
  [![Customer cabinet](https://img.shields.io/badge/CUSTOMER_CABINET-0F172A?style=for-the-badge)](https://autora-service.onrender.com/client/)
  [![CI](https://img.shields.io/github/actions/workflow/status/webnix-technologygroup/autora-service/ci.yml?style=for-the-badge&label=CI)](https://github.com/webnix-technologygroup/autora-service/actions/workflows/ci.yml)

  <br>

  ![Django](https://img.shields.io/badge/Django_5.2-0C4B33?logo=django&logoColor=white)
  ![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
  ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-4169E1?logo=postgresql&logoColor=white)
  ![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=111827)

  <br>

  [Product](#product) · [Customer cabinet](#customer-cabinet) · [Staff workspace](#staff-workspace) · [Engineering](#engineering) · [Run locally](#run-locally)
</div>

<br>

<img src="./docs/screenshots/01-home-desktop.jpg" alt="AUTORA public website" width="100%">

<p align="center"><sub>Responsive public website and online service booking</sub></p>

<br>

## Product

AUTORA is a production-style Django application for a modern automotive workshop. It connects three distinct experiences in one system:

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>Customer</h3>
      Book a service<br>
      Save multiple orders<br>
      Track repair progress<br>
      Review and approve estimates<br>
      Read in-app updates
    </td>
    <td width="33%" valign="top">
      <h3>Workshop team</h3>
      Process incoming requests<br>
      Assign responsible staff<br>
      Schedule appointments<br>
      Build estimates<br>
      Publish customer-visible events
    </td>
    <td width="33%" valign="top">
      <h3>System</h3>
      Role-based permissions<br>
      Private media access<br>
      Audit-friendly event history<br>
      Rate limits and CSRF protection<br>
      PostgreSQL-backed persistence
    </td>
  </tr>
</table>

> **Portfolio demo:** all seeded customers, vehicles, orders, prices, and contact details are fictional.

<br>

## Customer cabinet

No registration. No password. No Google or OAuth account.

A customer adds an order using its **order number**. Django keeps authorized orders in a server-side browser session, allowing several orders to live in one cabinet without exposing access data through `localStorage`.

<br>

<table>
  <tr>
    <td width="50%">
      <img src="./docs/screenshots/05-client-cabinet.jpg" alt="AUTORA customer cabinet">
    </td>
    <td width="50%">
      <img src="./docs/screenshots/06-client-order.jpg" alt="AUTORA customer order details">
    </td>
  </tr>
  <tr>
    <td align="center"><sub><strong>One browser, multiple saved orders</strong></sub></td>
    <td align="center"><sub><strong>Status, estimate, timeline, and notifications</strong></sub></td>
  </tr>
</table>

<br>

**Customer flow**

```text
Submit request  →  Receive order number  →  Add to cabinet  →  Follow progress  →  Approve estimate
```

<br>

## Staff workspace

A focused operational interface separate from Django Admin. Staff can manage daily workshop work without touching system-level configuration.

<img src="./docs/screenshots/07-staff-dashboard.jpg" alt="AUTORA staff dashboard" width="100%">

<p align="center"><sub>Operational dashboard with workload and order-state visibility</sub></p>

<br>

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>Order operations</h3>
      Status transitions<br>
      Staff assignment<br>
      Appointment scheduling<br>
      Internal comments<br>
      Customer-visible history
    </td>
    <td width="50%" valign="top">
      <h3>Finance and access</h3>
      Estimate line items<br>
      Approval state<br>
      Final pricing<br>
      Client-link management<br>
      Notification retry controls
    </td>
  </tr>
</table>

<img src="./docs/screenshots/09-staff-order-detail.jpg" alt="AUTORA staff order workspace" width="100%">

<p align="center"><sub>One workspace for schedule, responsibility, estimates, comments, and history</sub></p>

<br>

## System administration

Django Admin remains the system-level control surface for services, customers, vehicles, orders, events, access links, estimates, and notifications.

<img src="./docs/screenshots/10-django-admin.jpg" alt="Customized AUTORA Django Admin" width="100%">

<p align="center"><sub>Customized Django Admin · users are created only with <code>createsuperuser</code></sub></p>

<br>

## Interface gallery

The primary story stays visible above. Supporting screens are grouped below to keep the page easy to scan.

<details>
<summary><strong>Public booking journey</strong></summary>

<br>

<table>
  <tr>
    <td width="50%"><img src="./docs/screenshots/02-services-desktop.jpg" alt="AUTORA service catalogue"></td>
    <td width="50%"><img src="./docs/screenshots/03-booking-form.jpg" alt="AUTORA booking form"></td>
  </tr>
  <tr>
    <td align="center"><sub>Service catalogue</sub></td>
    <td align="center"><sub>Booking form</sub></td>
  </tr>
</table>

<br>

<img src="./docs/screenshots/04-booking-success.jpg" alt="AUTORA booking success screen" width="100%">

<p align="center"><sub>Successful request and private order number</sub></p>

</details>

<br>

<details>
<summary><strong>Staff order management</strong></summary>

<br>

<img src="./docs/screenshots/08-staff-orders.jpg" alt="AUTORA staff order list" width="100%">

<p align="center"><sub>Searchable and filterable workshop order queue</sub></p>

</details>

<br>

<details>
<summary><strong>Responsive mobile experience</strong></summary>

<br>

<table>
  <tr>
    <td width="33%"><img src="./docs/screenshots/11-home-mobile.jpg" alt="AUTORA mobile home"></td>
    <td width="33%"><img src="./docs/screenshots/12-client-cabinet-mobile.jpg" alt="AUTORA mobile customer cabinet"></td>
    <td width="33%"><img src="./docs/screenshots/13-staff-mobile.jpg" alt="AUTORA mobile staff workspace"></td>
  </tr>
  <tr>
    <td align="center"><sub>Public UI</sub></td>
    <td align="center"><sub>Customer cabinet</sub></td>
    <td align="center"><sub>Staff workspace</sub></td>
  </tr>
</table>

</details>

<br>

<details>
<summary><strong>Custom error states</strong></summary>

<br>

<img src="./docs/screenshots/14-error-404.jpg" alt="Custom AUTORA 404 page" width="100%">

<p align="center"><sub>Branded 403, 404, and 500 experience</sub></p>

</details>

<br>

## Engineering

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>Application</h3>
      <strong>Backend</strong> · Django 5.2<br>
      <strong>Database</strong> · PostgreSQL on Neon<br>
      <strong>Server</strong> · Gunicorn<br>
      <strong>Static assets</strong> · WhiteNoise<br>
      <strong>Frontend</strong> · Templates, CSS, vanilla JS, SVG
    </td>
    <td width="50%" valign="top">
      <h3>Delivery</h3>
      <strong>Hosting</strong> · Render Web Service<br>
      <strong>Database TLS</strong> · <code>sslmode=require</code><br>
      <strong>Health check</strong> · <code>/readiness/</code><br>
      <strong>Automation</strong> · GitHub Actions<br>
      <strong>Demo setup</strong> · idempotent seed command
    </td>
  </tr>
</table>

### Architecture

```text
Public site ─┐
Customer UI ─┼──► Django / Gunicorn on Render ──TLS──► Neon PostgreSQL
Staff UI ────┤              │
Admin ───────┘              ├── WhiteNoise static assets
                            └── Authorization-checked private media
```

### Security model

- Secure, HttpOnly, SameSite session cookies
- CSRF token and trusted-origin validation for unsafe requests
- Same-origin normalization for opaque Render form submissions without disabling CSRF
- HTTPS redirect, HSTS, CSP, frame denial, and content-type protection
- Private order media served only after authorization checks
- Rate limits for booking and cabinet lookup
- Production secrets validated and loaded only from environment variables

<br>

## Demo

**Live application:** https://autora-service.onrender.com/

Use any seeded order number in the customer cabinet:

```text
DEMO-26-001
DEMO-26-002
DEMO-26-003
DEMO-26-004
```

No phone number is required. Public staff and admin credentials are intentionally not included.

<br>

## Run locally

<details open>
<summary><strong>Windows PowerShell</strong></summary>

```powershell
git clone https://github.com/webnix-technologygroup/autora-service.git
cd autora-service

py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$env:DJANGO_ENV="development"
$env:DJANGO_DEBUG="1"
$env:DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,testserver"
$env:PUBLIC_BASE_URL="http://127.0.0.1:8000"
$env:CLIENT_TOKEN_ENCRYPTION_KEYS="local-development-encryption-key-change-me"
$env:EMAIL_ENABLED="0"
$env:SECURE_SSL_REDIRECT="0"
$env:TRUST_PROXY_HEADERS="0"
$env:TIME_ZONE="Europe/Kyiv"

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

</details>

<details>
<summary><strong>macOS / Linux</strong></summary>

```bash
git clone https://github.com/webnix-technologygroup/autora-service.git
cd autora-service
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

export DJANGO_ENV=development
export DJANGO_DEBUG=1
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
export PUBLIC_BASE_URL=http://127.0.0.1:8000
export CLIENT_TOKEN_ENCRYPTION_KEYS=local-development-encryption-key-change-me
export EMAIL_ENABLED=0
export SECURE_SSL_REDIRECT=0
export TRUST_PROXY_HEADERS=0
export TIME_ZONE=Europe/Kyiv

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

</details>

<br>

## Validate

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test service
python manage.py collectstatic --noinput
```

The suite covers booking, anonymous access, the multi-order cabinet, permissions, scheduling, estimates, notifications, CSRF behavior, and production settings.

<br>

## Deploy

<details>
<summary><strong>Render + Neon configuration</strong></summary>

### Build

```bash
bash build.sh
```

### Start

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers ${GUNICORN_WORKERS:-1} --timeout 60 --access-logfile - --error-logfile -
```

### Database

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT=5432
PGSSLMODE=require
```

`build.sh` installs dependencies, collects static files, applies migrations, and runs the idempotent demo seed. Production secrets stay in Render environment variables.

</details>

<br>

## Repository map

```text
config/              Django configuration and production settings
service/             Domain logic, customer access, staff UI, tests
service/static/      CSS, JavaScript, logos, and SVG artwork
templates/           Public, customer, staff, admin, and error UI
docs/screenshots/    Portfolio gallery
.github/workflows/   Continuous integration
build.sh             Render build and database preparation
render.yaml          Optional infrastructure-as-code setup
Dockerfile           Container deployment option
```

<br>

---

<div align="center">
  <img src="./service/static/service/logo-mark.svg" width="46" alt="AUTORA">
  <br><br>
  <strong>AUTORA</strong>
  <br>
  <sub>Designed and engineered as a complete Django portfolio case.</sub>
</div>
