# Notes

A Python FastAPI backend for a multi-user AI notes and reminder application. It supports OAuth sign-in, workspace management, WhatsApp interactions, scheduled reminders, AI agents, and Razorpay subscriptions.

## Features

- OAuth 2.0 authentication with Google, GitHub, and Microsoft
- JWT-based authenticated API access
- MongoDB-backed users, workspaces, reminders, payments, and subscriptions
- Multi-component personal workspace management
- AI responses through web and WhatsApp
- Text, image, and audio message handling through WhatsApp
- Scheduled reminder delivery with Celery and Redis
- Razorpay plans, checkout, webhooks, payments, cancellation, and grace-period handling
- Invoice generation and Notion integration

## Tech Stack

- **Framework:** FastAPI / Starlette
- **Database:** MongoDB with PyMongo
- **Task Queue:** Celery + Redis
- **Authentication:** OAuth 2.0, Authlib, python-jose JWT
- **AI:** Agno, LiteLLM, Anthropic, AWS Boto3, Crawl4AI
- **Messaging:** Meta WhatsApp Cloud API
- **Payments:** Razorpay
- **Integrations:** Notion

## Project Structure

| File | Purpose |
| --- | --- |
| `main.py` | FastAPI application and reminder endpoints |
| `auth.py` | OAuth login callbacks and JWT authentication |
| `api.py` | Workspace, signup, AI, invite, and API endpoints |
| `db.py` | MongoDB connection and data-access helpers |
| `models.py` | Pydantic authentication models |
| `dependencies.py` | Request authentication dependencies |
| `tasks.py` | Celery reminder workers and scheduled tasks |
| `subscriptions.py` | Razorpay subscription management and webhooks |
| `invoices.py` | Payment invoice generation |
| `whatsapp.py` | WhatsApp webhook and message processing |
| `ai.py` | AI agent definitions |
| `func.py` | Shared integration helpers |
| `notion.py` | Notion integration |

## Prerequisites

- Python 3.10 or newer
- MongoDB
- Redis
- Accounts and credentials for the integrations you intend to use

## Installation

1. Clone the repository:

```bash
git clone https://github.com/AnishNavali/notes.git
cd notes
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root.

## Environment Variables

Configure the services used by the application:

```dotenv
# Application
MONGO_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_EXPIRE_MINUTES=60
FRONTEND_URL=http://localhost:3000
APP_BASE_URL=http://localhost:8000

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# GitHub OAuth
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# Microsoft OAuth
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=common

# WhatsApp Cloud API
VERIFY_TOKEN=
WHATSAPP_TOKEN=
PHONE_NUMBER_ID=

# Razorpay
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
RAZORPAY_PLAN_FREE=
RAZORPAY_PLAN_BASIC=
RAZORPAY_PLAN_PRO=
SUBSCRIPTION_GRACE_DAYS=3

# AI and integration providers
ANTHROPIC_API_KEY=
NOTION_API_KEY=
```

> **Security:** Never commit real credentials. Keep `.env` private and rotate any secrets that have already been exposed.

## Running the API

Start the FastAPI development server:

```bash
uvicorn main:app --reload
```

The API is available at `http://localhost:8000`.

Interactive API documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Running Background Tasks

Start a Celery worker:

```bash
celery -A tasks.celery worker --loglevel=info
```

Start a worker for the `messages` queue:

```bash
celery -A tasks.celery worker -Q messages --loglevel=info
```

Start the Celery beat scheduler:

```bash
celery -A tasks.celery beat --loglevel=info
```

Redis must be running, and `REDIS_URL` must point to the broker used by Celery.

## Authentication

OAuth is available through provider-specific routes:

- `GET /auth/google/login`
- `GET /auth/github/login`
- `GET /auth/microsoft/login`

After a successful callback, the backend redirects to `FRONTEND_URL` with a JWT in the `token` query parameter.

Register the corresponding callback URLs with each OAuth provider:

```text
APP_BASE_URL/auth/google/callback
APP_BASE_URL/auth/github/callback
APP_BASE_URL/auth/microsoft/callback
```

## API Highlights

- `GET /auth/me` — authenticated user details
- `GET /api/get_workspace` — retrieve the current user's workspace
- `POST /api/add_to_workspace` — add a workspace component
- `POST /api/update_workspace` — update a workspace component
- `DELETE /api/delete_component` — delete a workspace component
- `POST /api/llm` — send a message to the AI agent
- `POST /reminders` — create a reminder
- `GET /users/me/reminders` — list authenticated user reminders
- `GET /reminders/{reminder_id}` — retrieve a reminder
- `GET /api/subscriptions/plans` — list subscription plans
- `POST /api/subscriptions/create` — create a Razorpay subscription
- `POST /api/subscriptions/webhook` — receive Razorpay webhook events

## Scheduled Tasks

The Celery beat configuration includes:

- Reminder heartbeat check every minute
- Subscription grace-period check every hour

## Razorpay Configuration

Configure the Basic and Pro plan IDs in Razorpay, then set their IDs in `.env`. Register the webhook endpoint with Razorpay:

```text
https://your-domain.example/api/subscriptions/webhook
```

Enable the subscription and payment events used by `subscriptions.py`.

## Development Notes

- The MongoDB database name is currently `reminders_db`.
- Reminder timestamps should be supplied as ISO 8601 strings.
- CORS is currently configured to allow all origins.
- OAuth callback results are redirect-based rather than returning JSON by default.
- Local Celery scheduling requires both a worker and the beat process.

## License

No license has been specified for this repository.
