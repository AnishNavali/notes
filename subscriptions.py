"""
subscriptions.py – Razorpay subscription management for Free / Basic / Pro tiers.

Flow:
  1. Frontend calls POST /subscriptions/create  → gets back razorpay_subscription_id
  2. Frontend opens Razorpay checkout JS with that id
  3. User completes payment on Razorpay
  4. Razorpay fires webhook events to POST /subscriptions/webhook
  5. Backend updates user subscription state in MongoDB

Environment variables required (see .env):
  RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
  RAZORPAY_PLAN_FREE, RAZORPAY_PLAN_BASIC, RAZORPAY_PLAN_PRO
  SUBSCRIPTION_GRACE_DAYS  (default: 3)
"""

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import razorpay
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

import db
from dependencies import CurrentUser
from invoices import generate_and_send_invoice

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
GRACE_DAYS = int(os.getenv("SUBSCRIPTION_GRACE_DAYS", "3"))

PLAN_IDS = {
    "free": os.getenv("RAZORPAY_PLAN_FREE", ""),
    "basic": os.getenv("RAZORPAY_PLAN_BASIC", ""),
    "pro": os.getenv("RAZORPAY_PLAN_PRO", ""),
}

# Static plan metadata shown to the frontend
PLAN_CATALOG = {
    "free": {
        "name": "Free",
        "price": 0,
        "currency": "INR",
        "billing_cycle": None,
        "features": [
            "Workspace (read-only)",
            "Up to 5 reminders",
            "WhatsApp bot (limited)",
        ],
    },
    "basic": {
        "name": "Basic",
        "price": 99,
        "currency": "INR",
        "billing_cycle": "monthly",
        "features": [
            "Full workspace access",
            "Unlimited reminders",
            "WhatsApp bot",
            "Email support",
        ],
    },
    "pro": {
        "name": "Pro",
        "price": 499,
        "currency": "INR",
        "billing_cycle": "monthly",
        "features": [
            "Everything in Basic",
            "AI agent (web + WhatsApp)",
            "Priority support",
            "Early access to new features",
        ],
    },
}


def _razorpay_client() -> razorpay.Client:
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay is not configured. Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in .env",
        )
    return razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_subscription(email: str) -> dict:
    """Return the subscription subdoc for a user, defaulting to free/active."""
    user = db.get_one(collection="users", key={"email": email})
    if user and user.get("subscription"):
        return user["subscription"]
    else:
        return {
            "plan": "free",
            "status": "active",
            "razorpay_subscription_id": None,
            "razorpay_customer_id": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "grace_period_end": None,
        }


def _set_subscription(email: str, sub: dict):
    db.save(collection="users", key={"email": email}, doc={"subscription": sub})


def _unix_to_dt(ts) -> datetime | None:
    """Convert a Razorpay Unix timestamp to a UTC datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Verify the X-Razorpay-Signature header using HMAC-SHA256."""
    if not RAZORPAY_WEBHOOK_SECRET:
        return False
    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _email_from_subscription_id(razorpay_subscription_id: str) -> str | None:
    """Look up the user email that owns this Razorpay subscription."""
    user = db.get_one(
        collection="users",
        key={"subscription.razorpay_subscription_id": razorpay_subscription_id},
    )
    if user:
        return user.get("email")
    return None


def _record_payment(
    email: str,
    event: str,
    razorpay_subscription_id: str,
    razorpay_payment_id: str | None = None,
    amount: int | None = None,  # in paise (INR smallest unit)
    currency: str = "INR",
    status: str = "captured",
    failure_reason: str | None = None,
    plan: str | None = None,
    invoice_number: str | None = None,
):
    """Insert a payment record into the payments collection."""
    doc = {
        "email": email,
        "event": event,
        "razorpay_subscription_id": razorpay_subscription_id,
        "razorpay_payment_id": razorpay_payment_id,
        "amount": amount,
        "amount_display": f"{amount / 100:.2f} {currency}" if amount else None,
        "currency": currency,
        "status": status,
        "failure_reason": failure_reason,
        "plan": plan,
        "invoice_number": invoice_number,
        "created_at": datetime.now(timezone.utc),
    }
    db.insert(collection="payments", doc=doc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/plans")
def get_plans():
    """Return all plan details. Public — no auth required."""
    return PLAN_CATALOG


@router.get("/status")
def get_status(current_user: CurrentUser):
    """Return the authenticated user's current subscription state."""
    email = current_user.get("email", "")
    sub = _get_subscription(email)
    if sub["plan"] == "basic":
        cost = "INR 99"
    elif sub["plan"] == "pro":
        cost = "INR 499"
    else:
        cost = "INR 0"
    return {"type": sub, "cost": cost}


@router.get("/payments")
def get_payment_history(current_user: CurrentUser):
    """Return the full payment history for the authenticated user."""
    email = current_user.get("email", "")
    records = db.query(
        collection="payments",
        query={"email": email},
    )
    # Sort newest first (query() strips _id so sort in Python)
    records.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"payments": records}


class CreateSubscriptionRequest(BaseModel):
    plan: str  # "basic" | "pro"


@router.post("/create")
def create_subscription(data: CreateSubscriptionRequest, current_user: CurrentUser):
    """
    Create a Razorpay subscription for the user.
    Returns { razorpay_subscription_id, razorpay_key_id } for the frontend checkout.
    """
    if data.plan not in ("basic", "pro"):
        raise HTTPException(
            status_code=400,
            detail="Invalid plan. Choose 'basic' or 'pro'.",
        )

    plan_id = PLAN_IDS.get(data.plan)
    if not plan_id:
        raise HTTPException(
            status_code=503,
            detail=f"Razorpay plan ID for '{data.plan}' is not configured.",
        )

    email = current_user.get("email", "")

    # Prevent creating a duplicate active subscription
    existing = _get_subscription(email)
    if (
        existing.get("status") == "active"
        and existing.get("plan") == data.plan
        and existing.get("razorpay_subscription_id")
    ):
        raise HTTPException(
            status_code=409,
            detail=f"You already have an active '{data.plan}' subscription.",
        )

    client = _razorpay_client()

    try:
        subscription = client.subscription.create(
            {
                "plan_id": plan_id,
                "total_count": 12,  # 12 billing cycles (1 year); adjust as needed
                "quantity": 1,
                "notify_info": {
                    "notify_phone": current_user.get("phone", ""),
                    "notify_email": email,
                },
            }
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}") from e

    # Persist the subscription id immediately so webhook can find the user
    sub = _get_subscription(email)
    sub["razorpay_subscription_id"] = subscription["id"]
    sub["plan"] = data.plan
    sub["status"] = "created"  # not yet active — waiting for first payment
    _set_subscription(email, sub)

    return {
        "razorpay_subscription_id": subscription["id"],
        "razorpay_key_id": RAZORPAY_KEY_ID,
    }


class ConfirmPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_subscription_id: str
    razorpay_signature: str


@router.post("/confirm")
def confirm_payment(data: ConfirmPaymentRequest, current_user: CurrentUser):
    """
    Verify the Razorpay payment signature returned to the frontend handler
    and activate the subscription immediately — without waiting for the webhook.

    The webhook (subscription.activated) still fires afterward and acts as a
    safety net. If both run, the second write is idempotent (same values).

    Signature formula (Razorpay docs):
        HMAC-SHA256(payment_id + "|" + subscription_id, RAZORPAY_KEY_SECRET)
    """
    if not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Razorpay is not configured.",
        )

    # --- verify signature -------------------------------------------------
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg=f"{data.razorpay_payment_id}|{data.razorpay_subscription_id}".encode(
            "utf-8"
        ),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, data.razorpay_signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature. Payment could not be verified.",
        )

    # --- signature valid — activate subscription -------------------------
    email = current_user.get("email", "")
    sub = _get_subscription(email)

    # Guard: only activate if this subscription ID matches what we have on file
    if sub.get("razorpay_subscription_id") != data.razorpay_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription ID does not match the current user's subscription.",
        )

    now = datetime.now(timezone.utc)
    sub["status"] = "active"
    sub["cancel_at_period_end"] = False
    sub["grace_period_end"] = None
    _set_subscription(email, sub)

    # Record the confirmed payment
    _record_payment(
        email=email,
        event="payment.confirmed",
        razorpay_subscription_id=data.razorpay_subscription_id,
        razorpay_payment_id=data.razorpay_payment_id,
        status="captured",
        plan=sub.get("plan"),
    )

    return {
        "verified": True,
        "plan": sub.get("plan"),
        "status": sub.get("status"),
    }


@router.post("/cancel")
def cancel_subscription(current_user: CurrentUser):
    """
    Cancel the user's subscription at the end of the current billing period.
    Access continues until current_period_end.
    """
    email = current_user.get("email", "")
    sub = _get_subscription(email)

    if sub.get("plan") == "free" or not sub.get("razorpay_subscription_id"):
        raise HTTPException(
            status_code=400, detail="No active paid subscription to cancel."
        )

    if sub.get("cancel_at_period_end"):
        raise HTTPException(
            status_code=409,
            detail="Subscription is already scheduled for cancellation.",
        )

    if sub.get("status") == "expired":
        raise HTTPException(status_code=400, detail="Subscription has already expired.")

    client = _razorpay_client()

    try:
        # cancel_at_cycle_end=1 means Razorpay cancels after the current cycle
        client.subscription.cancel(
            sub["razorpay_subscription_id"],
            {"cancel_at_cycle_end": 1},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}") from e

    sub["cancel_at_period_end"] = True
    _set_subscription(email, sub)

    return {
        "message": "Subscription will be cancelled at the end of the current billing period.",
        "current_period_end": sub.get("current_period_end"),
    }


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------


@router.post("/webhook")
async def razorpay_webhook(request: Request):
    """
    Receive and process Razorpay subscription events.
    Verified via HMAC-SHA256 signature on X-Razorpay-Signature header.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not _verify_webhook_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    import json

    payload = json.loads(raw_body)

    event = payload.get("event")
    entity = payload.get("payload", {})

    # Most events carry the subscription under payload.subscription.entity
    sub_entity = entity.get("subscription", {}).get("entity", {})
    # Payment events carry it under payload.payment.entity + payload.subscription.entity
    payment_entity = entity.get("payment", {}).get("entity", {})

    razorpay_subscription_id = sub_entity.get("id") or payment_entity.get(
        "subscription_id"
    )

    if not razorpay_subscription_id:
        # Not a subscription event we care about — acknowledge and ignore
        return {"status": "ignored"}

    email = _email_from_subscription_id(razorpay_subscription_id)
    if not email:
        # Unknown subscription — could be a test event or data mismatch
        return {"status": "unknown_subscription"}

    sub = _get_subscription(email)
    now = datetime.now(timezone.utc)

    # ---- subscription.activated ----------------------------------------
    if event == "subscription.activated":
        sub["status"] = "active"
        sub["plan"] = _plan_from_razorpay_id(sub_entity.get("plan_id"))
        sub["current_period_end"] = _unix_to_dt(sub_entity.get("current_end"))
        sub["cancel_at_period_end"] = False
        sub["grace_period_end"] = None
        sub["razorpay_customer_id"] = sub_entity.get("customer_id")
        # No invoice here — subscription.charged fires for the same first payment
        # and handles invoice generation for all payments (first + recurring)
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            razorpay_payment_id=payment_entity.get("id"),
            amount=payment_entity.get("amount"),
            currency=payment_entity.get("currency", "INR"),
            status="captured",
            plan=sub["plan"],
            invoice_number=None,
        )

    # ---- subscription.charged (successful recurring payment) -----------
    elif event == "subscription.charged":
        sub["status"] = "active"
        sub["current_period_end"] = _unix_to_dt(sub_entity.get("current_end"))
        sub["cancel_at_period_end"] = sub_entity.get("cancel_at_cycle_end", False)
        sub["grace_period_end"] = None  # clear any previous grace period
        amount = payment_entity.get("amount")
        invoice_number = (
            generate_and_send_invoice(
                email=email,
                payment_id=payment_entity.get("id"),
                amount_paise=amount or 0,
                plan=sub.get("plan", ""),
                currency=payment_entity.get("currency", "INR"),
            )
            if amount
            else None
        )
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            razorpay_payment_id=payment_entity.get("id"),
            amount=amount,
            currency=payment_entity.get("currency", "INR"),
            status="captured",
            plan=sub.get("plan"),
            invoice_number=invoice_number,
        )
        user_data = db.get_one(collection="users", key={"email": email})
        # total_tokens = user_data["input_tokens"] + user_data["output_tokens"]
        db.save(
            collection="users",
            key={"email": email},
            doc={"input_tokens": 0, "output_tokens": 0},
        )

    # ---- subscription.cancelled ----------------------------------------
    # Razorpay fires this when cancel_at_cycle_end triggers at period end.
    # Access is already expired at this point.
    elif event == "subscription.cancelled":
        sub["status"] = "expired"
        sub["plan"] = "free"
        sub["cancel_at_period_end"] = False
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            status="cancelled",
            plan=sub.get("plan"),
        )

    # ---- subscription.completed ----------------------------------------
    # All billing cycles exhausted naturally.
    elif event == "subscription.completed":
        sub["status"] = "expired"
        sub["plan"] = "free"
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            status="completed",
            plan=sub.get("plan"),
        )

    # ---- subscription.halted -------------------------------------------
    # Razorpay retried payment multiple times and gave up.
    elif event == "subscription.halted":
        sub["status"] = "expired"
        sub["plan"] = "free"
        sub["grace_period_end"] = None
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            razorpay_payment_id=payment_entity.get("id"),
            amount=payment_entity.get("amount"),
            currency=payment_entity.get("currency", "INR"),
            status="failed",
            failure_reason="subscription_halted — all retries exhausted",
            plan=sub.get("plan"),
        )

    # ---- payment.failed ------------------------------------------------
    elif event == "payment.failed":
        if sub.get("status") == "created":
            # First payment never succeeded — wipe subscription back to free/empty
            sub["status"] = "free"
            sub["plan"] = "free"
            sub["razorpay_subscription_id"] = None
            sub["razorpay_customer_id"] = None
            sub["current_period_end"] = None
            sub["cancel_at_period_end"] = False
            sub["grace_period_end"] = None
        elif sub.get("status") in ("active", "grace_period"):
            # Recurring payment failed — start grace period
            sub["status"] = "grace_period"
            sub["grace_period_end"] = now + timedelta(days=GRACE_DAYS)
        _record_payment(
            email=email,
            event=event,
            razorpay_subscription_id=razorpay_subscription_id,
            razorpay_payment_id=payment_entity.get("id"),
            amount=payment_entity.get("amount"),
            currency=payment_entity.get("currency", "INR"),
            status="failed",
            failure_reason=(
                payment_entity.get("error_description")
                or payment_entity.get("error_code")
            ),
            plan=sub.get("plan"),
        )

    else:
        # Unhandled event type — acknowledge without error
        return {"status": "unhandled_event", "event": event}

    _set_subscription(email, sub)
    return {"status": "ok", "event": event}


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _plan_from_razorpay_id(razorpay_plan_id: str | None) -> str:
    """Reverse-lookup plan name from Razorpay plan ID."""
    for name, pid in PLAN_IDS.items():
        if pid and pid == razorpay_plan_id:
            return name
    return "free"
