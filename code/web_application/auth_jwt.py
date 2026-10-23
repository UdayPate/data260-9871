"""
DATA-260 Homework 7 - Part 1: JWT bearer authentication and role-based authorization.

Replaces the HW4 server-side session cookie on the domain API routes (the session code survives
only at the `hw4` tag). Passwords are bcrypt hashes in the MySQL `users` table; a token is issued
only after the password has been verified against that hash.

  POST /auth/login   {username, password} -> {access_token, token_type, expires_in, user}  | 401
  GET  /auth/me      Authorization: Bearer <jwt>  -> {id, username, name, email, role}      | 401

The same two endpoints are also served under /api/auth/* so the React client's base URL keeps working.

Roles: reader (read only), writer (read, create, update), moderator (everything incl. delete).
  - 401 = no token, an invalid/tampered token, an expired token, or bad login credentials
  - 403 = a valid token whose role is not allowed for the route
The role is read from the database on every request (not trusted from the token), so demoting a
user takes effect immediately.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from db import get_db  # importing db also loads code/web_application/.env into os.environ
from models import User

log = logging.getLogger("auth_jwt")

ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "30"))
ROLES = ("reader", "writer", "moderator")

_secret = os.environ.get("JWT_SECRET")
if not _secret:
    # No secret configured: use a random one for this process only. Tokens then stop working after
    # a restart, which is safe (never a guessable default) but inconvenient - set JWT_SECRET in .env.
    _secret = secrets.token_urlsafe(48)
    log.warning("JWT_SECRET is not set; using a random per-process secret")
JWT_SECRET = _secret

# Demo accounts (development only). league_admin is the HW4/HW5 admin, now a moderator.
DEMO_USERS = [
    ("league_admin", "League Admin", "league_admin@example.com", "moderator", "GoLions2026!"),
    ("reader_user", "Rita Reader", "reader@example.com", "reader", "Reader2026!"),
    ("writer_user", "Walt Writer", "writer@example.com", "writer", "Writer2026!"),
    ("moderator_user", "Maya Moderator", "moderator@example.com", "moderator", "Moderator2026!"),
]

# Verified against when the username does not exist, so a wrong username and a wrong password
# take about the same time (no user-enumeration timing leak).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # bcrypt rejects passwords over 72 bytes - treat as a failed login
        return False


def seed_demo_users(db: DBSession) -> None:
    """Idempotent: create any missing demo user; upgrade the legacy admin row (found by e-mail) in place."""
    for username, name, email, role, password in DEMO_USERS:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = db.query(User).filter(User.email == email).first()
        if user is None:
            db.add(User(username=username, name=name, email=email, role=role,
                        password_hash=hash_password(password)))
        elif not user.username:
            user.username, user.role = username, role
    db.commit()


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "username": user.username, "role": user.role,
               "iat": now, "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: DBSession = Depends(get_db),
) -> User:
    """401 unless the request carries a valid, unexpired token for a user that still exists."""
    if credentials is None:
        raise _unauthorized("Not authenticated")
    try:
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")
    try:
        user = db.get(User, int(claims["sub"]))
    except (TypeError, ValueError):
        user = None
    if user is None:
        raise _unauthorized("Invalid token")
    return user


def require_roles(*allowed: str):
    """Dependency factory: 401 if unauthenticated (via get_current_user), 403 if the role is not allowed."""
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden: requires role {' or '.join(allowed)} (you are '{user.role}')")
        return user
    return dependency


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def user_to_dict(user: User) -> dict:
    return {"id": user.id, "username": user.username, "name": user.name,
            "email": user.email, "role": user.role}


def login(payload: LoginRequest, db: DBSession = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    ok = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok:
        raise _unauthorized("Invalid username or password")   # same message for both cases
    return {"access_token": create_access_token(user), "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60, "user": user_to_dict(user)}


def me(user: User = Depends(get_current_user)):
    return user_to_dict(user)


def _make_router() -> APIRouter:
    r = APIRouter()
    r.add_api_route("/auth/login", login, methods=["POST"], tags=["auth"])
    r.add_api_route("/auth/me", me, methods=["GET"], tags=["auth"])
    return r


router = _make_router()       # served at /auth/login and /auth/me  (the paths in the assignment)
api_router = _make_router()   # included with prefix /api for the React client
