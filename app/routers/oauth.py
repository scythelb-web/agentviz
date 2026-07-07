"""OAuth routes — Stripe Connect integration."""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.stripe import get_oauth_url, handle_oauth_callback

router = APIRouter(tags=["oauth"])


@router.get("/oauth/connect")
async def connect_stripe(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    url = get_oauth_url(user["id"])
    return RedirectResponse(url, status_code=303)


@router.get("/oauth/callback")
async def oauth_callback(request: Request, code: str, state: str):
    try:
        user_id = int(state)
    except (ValueError, TypeError):
        return RedirectResponse("/auth/login", status_code=303)

    oauth_data = handle_oauth_callback(code)

    with get_db() as db:
        db.execute(
            """UPDATE users SET stripe_account_id = ?, stripe_access_token = ?,
               stripe_refresh_token = ? WHERE id = ?""",
            (oauth_data["stripe_user_id"], oauth_data["access_token"],
             oauth_data["refresh_token"], user_id),
        )

        # Log sync
        db.execute(
            "INSERT INTO sync_log (user_id, stripe_account_id, status) VALUES (?, ?, ?)",
            (user_id, oauth_data["stripe_user_id"], "running"),
        )

        # Initial sync
        from app.services.stripe import sync_agent_transactions
        count = sync_agent_transactions(
            oauth_data["stripe_user_id"],
            oauth_data["access_token"],
            user_id,
            db,
        )

        db.execute(
            "UPDATE sync_log SET status = 'completed', transactions_synced = ?, completed_at = CURRENT_TIMESTAMP WHERE user_id = ? AND status = 'running'",
            (count, user_id),
        )

    return RedirectResponse("/dashboard?connected=1", status_code=303)


@router.post("/oauth/sync")
async def sync_now(request: Request):
    user = get_current_user(request)
    if not user or not user["stripe_access_token"]:
        return RedirectResponse("/dashboard", status_code=303)

    with get_db() as db:
        db.execute(
            "INSERT INTO sync_log (user_id, stripe_account_id, status) VALUES (?, ?, ?)",
            (user["id"], user["stripe_account_id"], "running"),
        )

        from app.services.stripe import sync_agent_transactions
        count = sync_agent_transactions(
            user["stripe_account_id"],
            user["stripe_access_token"],
            user["id"],
            db,
        )

        db.execute(
            "UPDATE sync_log SET status = 'completed', transactions_synced = ?, completed_at = CURRENT_TIMESTAMP WHERE user_id = ? AND status = 'running'",
            (count, user["id"]),
        )

    return RedirectResponse("/dashboard?synced=1", status_code=303)
