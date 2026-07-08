"""Stripe webhook handler — subscription lifecycle events."""

import json
import logging
from fastapi import APIRouter, Request, HTTPException
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stripe", tags=["stripe"])


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid payload")

    event_type = event.get("type", "")
    logger.info("Webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        if customer_id and subscription_id:
            with get_db() as db:
                user = db.execute(
                    "SELECT * FROM users WHERE stripe_customer_id = ?",
                    (customer_id,),
                ).fetchone()
                if user:
                    # Determine plan from subscription price amount
                    from app.config import STRIPE_SECRET_KEY
                    try:
                        import stripe as _stripe
                        _stripe.api_key = STRIPE_SECRET_KEY
                        sub = _stripe.Subscription.retrieve(subscription_id)
                        plan = "growth"
                        for k, v in {
                            "starter": 2900,
                            "growth": 7900,
                            "scale": 19900,
                        }.items():
                            if sub["items"]["data"][0]["price"].get("unit_amount") == v:
                                plan = k
                    except Exception:
                        plan = "growth"
                    db.execute(
                        "UPDATE users SET stripe_subscription_id = ?, plan = ? WHERE id = ?",
                        (subscription_id, plan, user["id"]),
                    )
                    logger.info(
                        "Subscription activated: %s plan=%s", user["email"], plan
                    )

    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        if sub.get("id"):
            with get_db() as db:
                db.execute(
                    "UPDATE users SET plan = 'starter', stripe_subscription_id = NULL WHERE stripe_subscription_id = ?",
                    (sub["id"],),
                )

    return {"status": "ok"}
