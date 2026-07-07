"""Settings routes — Stripe API key management."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def settings_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    connected = bool(user["stripe_access_token"]) if user else False

    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {"request": request, "connected": connected},
    )


@router.post("/settings/connect")
async def connect_api_key(request: Request, api_key: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    # Validate the key by hitting Stripe
    import stripe as _stripe
    _stripe.api_key = api_key
    try:
        account = _stripe.Account.retrieve()
        stripe_account_id = account.get("id", "")
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            "settings.html",
            {"request": request, "connected": False, "error": f"Invalid API key: {str(e)}"},
        )

    with get_db() as db:
        db.execute(
            "UPDATE users SET stripe_access_token = ?, stripe_account_id = ? WHERE id = ?",
            (api_key, stripe_account_id, user["id"]),
        )

    # Run initial sync
    try:
        from app.services.stripe import sync_agent_transactions_direct
        with get_db() as db:
            count = sync_agent_transactions_direct(api_key, stripe_account_id, user["id"], db)
    except Exception:
        count = 0

    return RedirectResponse("/dashboard?synced=1", status_code=303)


@router.post("/settings/disconnect")
async def disconnect(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    with get_db() as db:
        db.execute(
            "UPDATE users SET stripe_access_token = NULL, stripe_account_id = NULL WHERE id = ?",
            (user["id"],),
        )

    return RedirectResponse("/settings", status_code=303)
