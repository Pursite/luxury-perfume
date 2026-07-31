````markdown
# Wine Shop API

A backend REST API for a wine shop, built with Django, Django REST Framework, PostgreSQL, Redis, Celery, and JWT authentication.

The project currently focuses on two main domains:

- user authentication and profile management
- product catalogue management

It is being developed as a structured learning project with emphasis on clean architecture, security, testing, Git workflows, and maintainable Django practices.

---

## Current Features

### Users and Authentication

- username/password signup
- phone number/OTP signup
- username/password login
- phone number/OTP login
- password reset through OTP
- JWT access and refresh tokens
- refresh-token rotation
- refresh-token blacklisting
- logout through refresh-token blacklisting
- profile completion
- profile updates
- user addresses
- username-only accounts
- phone-only accounts
- accounts with both username and phone number

### Authentication Security

- global authenticated API default
- explicit public endpoints
- OTP expiry
- OTP replay prevention
- OTP failed-attempt tracking
- temporary OTP lockouts
- password-login failed-attempt tracking
- username/IP-scoped login lockouts
- request throttling
- generic authentication errors
- fail-closed Redis security cache

### Product Catalogue

- public product listing
- public product detail
- administrator-only product creation
- administrator-only product update
- administrator-only product deletion
- product categories
- nested category hierarchy
- category cycle prevention
- brands
- product images
- primary product image support
- public product UUID identifiers
- product search and ordering
- Redis-backed public catalogue caching

### Upload Security

- JPEG, PNG, and WebP validation
- actual image-content inspection through Pillow
- MIME/content consistency validation
- file-size limits
- image-dimension limits
- corrupt image rejection
- decompression-bomb protection
- filename sanitization

---

## Technology Stack

### Backend

- Python
- Django 6
- Django REST Framework
- Simple JWT

### Data and Infrastructure

- PostgreSQL
- Redis
- Celery
- Gunicorn

### Testing

- Pytest
- pytest-django
- pytest-cov
- factory_boy
- Faker

### Supporting Packages

- django-environ
- django-filter
- django-cors-headers
- django-redis
- Pillow
- psycopg

The exact dependency versions are pinned in `requirements.txt`.

---

## Architecture

The project follows a layered structure:

```text
HTTP request
    ↓
APIView
    ↓
Serializer
    ↓
Service or selector
    ↓
Model and database
    ↓
Serialized response
````

Main responsibilities:

* **Views** handle HTTP orchestration.
* **Serializers** validate input and represent output.
* **Services** contain business logic and mutations.
* **Selectors** contain reusable database reads.
* **Models** define persisted state and critical invariants.
* **Celery tasks** handle background operations.
* **`apps.lib`** contains reusable project-wide infrastructure.

Detailed architecture documentation is available in:

```text
docs/architecture.md
```

---

## Project Structure

```text
wine-shop/
├── apps/
│   ├── lib/
│   ├── products/
│   └── users/
├── config/
├── docs/
│   ├── api.md
│   ├── architecture.md
│   ├── authentication.md
│   ├── deployment.md
│   └── security.md
├── .env.example
├── AGENTS.md
├── manage.py
├── pytest.ini
├── README.md
└── requirements.txt
```

---

## Requirements

Before running the project locally, install:

* Python 3.12 or newer
* PostgreSQL
* Redis
* Git

Celery also depends on Redis in the current configuration.

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/Pursite/wine-shop.git
cd wine-shop
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Do not install the project dependencies globally into the operating system Python environment.

---

## Environment Configuration

Copy the example configuration:

```bash
cp .env.example .env
```

Then replace placeholder values in `.env`.

The real `.env` file must not be committed.

A minimal local configuration looks like:

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=wine_shop
DB_USER=wine_shop
DB_PASSWORD=replace-with-a-database-password
DB_HOST=localhost
DB_PORT=5432

REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

JWT_ACCESS_TOKEN_LIFETIME_MINUTES=20
JWT_REFRESH_TOKEN_LIFETIME_DAYS=30

OTP_EXPIRY_SECONDS=120
OTP_VERIFICATION_MAX_ATTEMPTS=5
OTP_VERIFICATION_LOCK_SECONDS=300

PASSWORD_LOGIN_MAX_ATTEMPTS=5
PASSWORD_LOGIN_LOCK_SECONDS=300

AUTH_ANON_THROTTLE_RATE=100/day
AUTH_USER_THROTTLE_RATE=1000/day
OTP_REQUEST_THROTTLE_RATE=1/m
OTP_VERIFY_THROTTLE_RATE=10/m
SIGNUP_THROTTLE_RATE=5/hour
PASSWORD_LOGIN_THROTTLE_RATE=10/m
```

The current `.env.example` contains the expected runtime configuration keys and placeholder values.

---

## PostgreSQL Setup

Create a local database and user.

Example:

```sql
CREATE DATABASE wine_shop;
CREATE USER wine_shop WITH PASSWORD 'your-password';
GRANT ALL PRIVILEGES ON DATABASE wine_shop TO wine_shop;
```

Use the same values in `.env`.

Do not run the application using the PostgreSQL superuser in production.

---

## Database Migrations

Apply migrations:

```bash
venv/bin/python manage.py migrate
```

Check migration state:

```bash
venv/bin/python manage.py showmigrations
```

Check whether model changes are missing migrations:

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

Migration files should be created, reviewed, tested, and committed to Git.

---

## Running Redis

Start Redis using the command appropriate for your system.

On many Linux systems:

```bash
sudo systemctl start redis-server
```

Verify Redis:

```bash
redis-cli ping
```

Expected result:

```text
PONG
```

Redis is required for:

* normal application caching
* OTP storage
* authentication failure counters
* temporary authentication lockouts
* Celery broker
* Celery result backend

Authentication-sensitive Redis failures intentionally return temporary service-unavailable responses.

---

## Running Celery

Start the Celery worker in a separate terminal:

```bash
venv/bin/celery -A config worker --loglevel=INFO
```

The Celery worker currently handles OTP delivery tasks.

Without a running worker, tasks may be queued but not delivered.

---

## Running the Development Server

Start Django:

```bash
venv/bin/python manage.py runserver
```

The API will normally be available at:

```text
http://127.0.0.1:8000/
```

Main API prefixes:

```text
/api/v1/users/
/api/v1/products/
```

---

## Authentication

The project supports two authentication methods.

### Username and Password

Users may:

* sign up with username/password
* log in immediately after signup
* authenticate without completing optional profile fields

### Phone Number and OTP

Users may:

* request a signup OTP
* verify the signup OTP
* request a login OTP
* verify the login OTP
* reset a password through OTP

A valid active user must have:

* a username
* or a phone number
* or both

An incomplete profile does not block authentication.

Detailed authentication behavior is documented in:

```text
docs/authentication.md
```

---

## JWT Usage

Protected requests must include:

```http
Authorization: Bearer <access-token>
```

The API returns access and refresh tokens after successful authentication.

Refresh-token rotation and blacklisting are enabled.

After a successful token refresh, clients should replace the previously stored refresh token.

---

## API Overview

### User endpoints

```text
POST /api/v1/users/signup/
POST /api/v1/users/signup/send-otp/
POST /api/v1/users/signup/verify-otp/

POST /api/v1/users/login/userpass/
POST /api/v1/users/login/send-otp/
POST /api/v1/users/login/verify-otp/

POST  /api/v1/users/profile/complete/
PATCH /api/v1/users/profile/update/

POST /api/v1/users/password-reset/send-otp/
POST /api/v1/users/password-reset/verify-and-reset/

POST /api/v1/users/logout/
```

### Product endpoints

```text
GET  /api/v1/products/
POST /api/v1/products/

GET    /api/v1/products/<product_uuid>/
PUT    /api/v1/products/<product_uuid>/
PATCH  /api/v1/products/<product_uuid>/
DELETE /api/v1/products/<product_uuid>/

POST   /api/v1/products/<product_uuid>/images/upload/
DELETE /api/v1/products/images/<image_id>/
```

User routes and product routes are registered under `/api/v1/` in the current project URL configuration.

Complete endpoint documentation is available in:

```text
docs/api.md
```

---

## Product Model Highlights

Products currently support:

* public UUID identifiers
* category
* optional brand
* SKU
* name and slug
* description
* regular price
* optional discount price
* stock
* alcohol by volume
* volume in millilitres
* country of origin
* vintage year
* bitterness index
* taste notes
* serving temperature
* active state
* featured state

The database ensures that a discount price is lower than the regular price.

Each product may have multiple images, but only one image may be marked as primary.

---

## Product Access Rules

Public users may:

* list active products
* retrieve active product details

Administrator or staff users may:

* create products
* update products
* delete products
* upload product images
* delete product images
* access inactive catalogue records where supported

The API is authenticated by default, while intentionally public catalogue reads explicitly permit anonymous access.

---

## Testing

Run all tests:

```bash
venv/bin/python -m pytest
```

Run Django system checks:

```bash
venv/bin/python manage.py check
```

Check migration consistency:

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

Run deployment checks:

```bash
venv/bin/python manage.py check --deploy
```

Before claiming a change is complete, run the tests relevant to that change and the complete suite where practical.

---

## Security

The project currently includes:

* authenticated access by default
* explicit public permissions
* staff-only product mutations
* JWT rotation and blacklisting
* password hashing
* OTP expiry
* OTP replay prevention
* OTP namespace isolation
* OTP failure counters
* temporary OTP lockouts
* password-login throttling
* username/IP-specific failed-login guards
* generic account-enumeration-resistant responses
* fail-closed authentication cache
* secure image validation
* database integrity constraints
* environment-based secret management

Detailed security documentation is available in:

```text
docs/security.md
```

---

## Deployment

The project includes Gunicorn and is designed to run with:

* PostgreSQL
* Redis
* Celery
* a reverse proxy such as Nginx
* persistent media storage

Detailed deployment guidance is available in:

```text
docs/deployment.md
```

The repository does not currently include:

* Dockerfile
* Docker Compose
* Kubernetes manifests
* CI/CD deployment configuration

These may be added later as separate features.

---

## Documentation

Project documentation is organized as follows:

| File                     | Purpose                                          |
| ------------------------ | ------------------------------------------------ |
| `README.md`              | Project overview, setup, and current status      |
| `docs/architecture.md`   | Internal architecture and layer responsibilities |
| `docs/authentication.md` | Authentication flows and identity rules          |
| `docs/api.md`            | Endpoint reference and access requirements       |
| `docs/security.md`       | Security controls and current limitations        |
| `docs/deployment.md`     | Production deployment guidance                   |
| `AGENTS.md`              | Repository instructions for coding agents        |

Documentation should be updated whenever:

* routes change
* configuration changes
* authentication behavior changes
* architecture changes
* deployment requirements change
* new applications are added

---

## Development Workflow

The recommended Git workflow is:

1. keep `main` stable
2. create one branch per feature
3. make focused commits
4. run tests
5. review the diff
6. merge through a pull request where practical

Example:

```bash
git switch main
git pull --ff-only
git switch -c feature/inventory
```

After implementation:

```bash
venv/bin/python -m pytest
git add .
git commit -m "Add inventory domain"
git push -u origin feature/inventory
```

---

## Project Status

Current stable domains:

* users
* authentication
* profiles
* products
* categories
* brands
* product images
* security hardening

The project is still under active development.

---

## Roadmap

Planned domains:

* [ ] inventory management
* [ ] shopping cart
* [ ] orders
* [ ] payments
* [ ] shipping
* [ ] reviews
* [ ] automated CI
* [ ] containerized development environment
* [ ] production health endpoint
* [ ] object storage integration

Roadmap entries describe planned work, not currently available functionality.

---

## Contributing

This is currently a solo learning project, but contributions may follow the same standards:

* preserve existing architecture
* avoid unrelated rewrites
* add or update tests
* keep API contracts stable
* update documentation
* never commit secrets
* use focused commits

Repository-specific coding-agent rules are documented in:

```text
AGENTS.md
```

---

## License

No license has been selected yet.

Until a license is added, normal copyright restrictions apply.

Add a `LICENSE` file before presenting the repository as open source.
