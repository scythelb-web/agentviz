"""Stripe service — OAuth, payment sync, agent transaction retrieval."""
import stripe
from app.config import STRIPE_SECRET_KEY, STRIPE_CLIENT_ID, BASE_URL

stripe.api_key = STRIPE_SECRET_KEY


def get_oauth_url(user_id: int) -> str:
    """Generate Stripe Connect OAuth URL."""
    return (
        f"https://connect.stripe.com/oauth/authorize"
        f"?response_type=code"
        f"&client_id={STRIPE_CLIENT_ID}"
        f"&scope=read_write"
        f"&state={user_id}"
        f"&redirect_uri={BASE_URL}/oauth/callback"
    )


def handle_oauth_callback(code: str) -> dict:
    """Exchange OAuth code for access token."""
    response = stripe.OAuth.token(
        grant_type="authorization_code",
        code=code,
    )
    return {
        "stripe_user_id": response["stripe_user_id"],
        "access_token": response["access_token"],
        "refresh_token": response.get("refresh_token", ""),
    }


def sync_agent_transactions(stripe_account_id: str, access_token: str, user_id: int, db) -> int:
    """Pull agent-tagged transactions from connected Stripe account.

    Stripe tags agentic commerce orders with metadata. We search PaymentIntents
    for agent-originated charges. The agent name appears in the PaymentIntent
    metadata under 'agent_name' or in the source description.
    """
    return _sync_transactions(access_token, stripe_account_id, user_id, db, via_connect=True)


def sync_agent_transactions_direct(api_key: str, stripe_account_id: str, user_id: int, db) -> int:
    """Pull agent-tagged transactions using a direct API key (not OAuth)."""
    return _sync_transactions(api_key, stripe_account_id, user_id, db, via_connect=False)


def _sync_transactions(api_key: str, stripe_account_id: str, user_id: int, db, via_connect: bool) -> int:
    import datetime
    count = 0

    # Look back 90 days for agent transactions
    created_after = int((datetime.datetime.now(datetime.timezone.utc) -
                         datetime.timedelta(days=90)).timestamp())

    try:
        # When using OAuth/Connect, pass stripe_account; for direct key, omit it
        list_kwargs = {
            "limit": 100,
            "created": {"gte": created_after},
        }
        if via_connect:
            list_kwargs["stripe_account"] = stripe_account_id

        # Use the provided api_key directly
        import stripe as _stripe
        _stripe.api_key = api_key

        payment_intents = _stripe.PaymentIntent.list(**list_kwargs)

        for pi in payment_intents.auto_paging_iter():
            metadata = pi.get("metadata", {}) or {}
            agent_name = metadata.get("agent_name") or metadata.get("agent_source")

            # Also check charges for agent-related descriptions
            if not agent_name and pi.get("charges"):
                charges = pi.charges.data if hasattr(pi.charges, 'data') else []
                for charge in charges[:1]:
                    desc = (charge.get("description") or "").lower()
                    if "agent" in desc:
                        agent_name = desc

            if agent_name:
                existing = db.execute(
                    "SELECT id FROM agent_transactions WHERE payment_intent_id = ?",
                    (pi["id"],),
                ).fetchone()

                if not existing:
                    db.execute(
                        """INSERT INTO agent_transactions
                           (user_id, stripe_account_id, payment_intent_id, amount,
                            currency, agent_name, customer_email, status, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            user_id,
                            stripe_account_id,
                            pi["id"],
                            pi["amount"],
                            pi.get("currency", "usd"),
                            agent_name,
                            pi.get("receipt_email", ""),
                            pi.get("status", "unknown"),
                            datetime.datetime.fromtimestamp(
                                pi["created"], tz=datetime.timezone.utc
                            ).isoformat(),
                        ),
                    )
                    count += 1

        return count
    except Exception as e:
        print(f"Sync error for account {stripe_account_id}: {e}")
        return count
