"""Auth routes — signup, login, logout."""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from passlib.hash import bcrypt
from jose import jwt
import datetime

from app.config import SECRET_KEY
from app.database import get_db

router = APIRouter(tags=["auth"])

ALGORITHM = "HS256"
COOKIE_NAME = "agentviz_session"


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        with get_db() as db:
            return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except Exception:
        return None


@router.get("/auth/login")
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse("login.html", {"request": request})


@router.post("/auth/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not user or not bcrypt.verify(password, user["password_hash"]):
            return request.app.state.templates.TemplateResponse(
                "login.html", {"request": request, "error": "Invalid email or password"}
            )
        token = create_token(user["id"], user["email"])
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(COOKIE_NAME, token, httponly=True, max_age=30*24*3600)
        return response


@router.get("/auth/signup")
async def signup_page(request: Request):
    return request.app.state.templates.TemplateResponse("signup.html", {"request": request})


@router.post("/auth/signup")
async def signup(request: Request, email: str = Form(...), password: str = Form(...)):
    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return request.app.state.templates.TemplateResponse(
                "signup.html", {"request": request, "error": "Email already registered"}
            )
        password_hash = bcrypt.hash(password)
        db.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
    return RedirectResponse("/auth/login", status_code=303)


@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
