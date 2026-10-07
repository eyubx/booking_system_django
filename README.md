# Booking System — Django REST Framework

Standalone Python backend based on the Spring Boot `BookingSystem` project. Includes users (ADMIN / EXPERT / USER), JWT login, expert profiles/search, appointment availability, booking creation/lookup/cancellation, Django admin, and Swagger documentation.

## Run locally

Requires Python 3.10+ (verified with Python 3.13).

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8081
```

The virtual environment and initial SQLite database have already been created during development. Create your own admin account with `createsuperuser`. This replaces the original public `create-admin` endpoint; all superusers receive the ADMIN role.

- API: http://localhost:8081/api/
- Interactive API docs: http://localhost:8081/api/docs/
- OpenAPI schema: http://localhost:8081/api/schema/
- Admin: http://localhost:8081/admin/

SQLite is the default. To use PostgreSQL, create an empty database and fill in `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in `.env`, then run migrations. `TIME_ZONE` controls the local appointment dates/times (default UTC).

## Endpoints

API endpoints accept paths with or without a trailing slash. Responses keep the original camelCase names and list endpoints return arrays.

| Method | Path | Access |
| --- | --- | --- |
| POST | `/api/users/register` | Public; creates USER accounts |
| POST | `/api/users/login` | Public; username and password |
| POST | `/api/token/refresh` | Public; refresh token |
| GET | `/api/users/me` | Authenticated |
| GET | `/api/users/` | Admin |
| POST | `/api/users/users/bulk` | Admin; array of registration objects |
| GET | `/api/experts/` | Public |
| POST | `/api/experts/` | Admin |
| GET | `/api/experts/search?name=...&expertise=...` | Public; case-insensitive substring filters |
| GET | `/api/experts/{id}` | Public |
| PATCH / DELETE | `/api/experts/{id}` | Admin or linked expert owner |
| GET | `/api/experts/{id}/availability?date=2026-12-01` | Public |
| POST | `/api/bookings/` | Public |
| GET | `/api/bookings/` | Admin sees all; other users see bookings for their own expert profile |
| GET | `/api/bookings/expert/{expertId}` | Admin or linked expert owner |
| GET | `/api/bookings/key/{key}` | Public with the unguessable booking reference |
| DELETE | `/api/bookings/{id}` | Admin or linked expert owner; frees the slot |

Login returns `{ "access": "...", "refresh": "...", "token": "...", "user": {...} }`; `token` is an alias for `access`. Send `Authorization: Bearer <access>` on protected requests. Passwords are hashed and excluded from every response.

## Example workflow

1. Create an admin with `createsuperuser` and log in through `/api/users/login`.
2. Register an expert's user account through `/api/users/register`:

```json
{"username": "alex", "email": "alex@example.com", "password": "A-Strong-Password-123!"}
```

3. As admin, create an expert profile using that user's ID:

```json
{
  "userId": 2,
  "name": "Alex Smith",
  "expertise": "Consulting",
  "description": "Business consultant",
  "email": "",
  "phone": "+1 555 123 4567",
  "availableHours": ["09:00", "10:00", "14:00"]
}
```

An empty or omitted expert email falls back to the linked user's email. Each user can have one expert profile. Owners can edit their profile but only admins can reassign its linked user. Creating a profile grants ownership-based access regardless of the linked user's role.

4. Query availability for a future date. The response contains `slots`, each with `time` and `available`.
5. Create an appointment:

```json
{
  "expertId": 1,
  "name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+1 555 987 6543",
  "note": "Initial consultation",
  "bookingDate": "2026-12-01",
  "timeSlot": "10:00"
}
```

Save the returned `key` to retrieve the confirmation later. Appointments must be in the future and use an offered HH:MM slot. A database uniqueness constraint prevents two appointments for the same expert/date/slot; conflicts return HTTP 409. Experts with bookings cannot be deleted (409).

## Existing React frontend

The existing frontend already targets `http://localhost:8081/api`; run Django on port 8081. CORS allows the default Vite development origins. The frontend's appointment screen currently uses mocked expert/availability data and has no submit handler; wire those controls to the availability and booking endpoints above. Login should store `response.data.token` or `response.data.access`.

## Verify

```sh
python manage.py check
python manage.py test
python manage.py spectacular --validate
```

Tests cover authentication, role escalation protection, expert ownership, partial updates, booking validation, database slot uniqueness, cancellation, search, and atomic bulk registration.
