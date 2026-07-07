"""Dashboard routes — analytics, charts, transaction views."""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)

    stripe_connected = bool(user.get("stripe_access_token"))

    with get_db() as db:
        # Agent breakdown
        agent_stats = db.execute(
            """SELECT agent_name,
                      COUNT(*) as tx_count,
                      SUM(amount) as total_revenue,
                      COUNT(CASE WHEN status = 'succeeded' THEN 1 END) as successful
               FROM agent_transactions
               WHERE user_id = ?
               GROUP BY agent_name
               ORDER BY total_revenue DESC""",
            (user["id"],),
        ).fetchall()

        # Monthly trend
        monthly = db.execute(
            """SELECT strftime('%Y-%m', created_at) as month,
                      SUM(amount) as revenue,
                      COUNT(*) as count
               FROM agent_transactions
               WHERE user_id = ?
               GROUP BY month
               ORDER BY month DESC LIMIT 12""",
            (user["id"],),
        ).fetchall()

        # Total stats
        totals = db.execute(
            """SELECT COUNT(*) as total_tx,
                      SUM(amount) as total_revenue,
                      COUNT(CASE WHEN status = 'succeeded' THEN 1 END) as successful_tx
               FROM agent_transactions WHERE user_id = ?""",
            (user["id"],),
        ).fetchone()

        # Recent transactions
        recent = db.execute(
            """SELECT * FROM agent_transactions
               WHERE user_id = ?
               ORDER BY created_at DESC LIMIT 20""",
            (user["id"],),
        ).fetchall()

        # Last sync
        last_sync = db.execute(
            """SELECT * FROM sync_log
               WHERE user_id = ? AND status = 'completed'
               ORDER BY completed_at DESC LIMIT 1""",
            (user["id"],),
        ).fetchone()

    # Calculate conversion rate
    total_tx = totals["total_tx"] if totals else 0
    successful_tx = totals["successful_tx"] if totals else 0
    conversion_rate = round(successful_tx / max(total_tx, 1) * 100, 1)

    total_revenue = (totals["total_revenue"] or 0) / 100  # cents to dollars

    data = {
        "request": request,
        "user": user,
        "stripe_connected": stripe_connected,
        "agent_stats": [dict(r) for r in agent_stats],
        "monthly": [dict(r) for r in reversed(monthly)],  # chronological
        "total_tx": total_tx,
        "total_revenue": total_revenue,
        "successful_tx": successful_tx,
        "conversion_rate": conversion_rate,
        "recent": [dict(r) for r in recent],
        "last_sync": dict(last_sync) if last_sync else None,
        "connected": request.query_params.get("connected"),
        "synced": request.query_params.get("synced"),
    }

    return request.app.state.templates.TemplateResponse("dashboard.html", data)
