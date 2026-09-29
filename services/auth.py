"""Bangumi identities and opaque, revocable server-side sessions."""

import hashlib
import logging
import os
import secrets
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

SESSION_COOKIE = "animescore_session"
STATE_COOKIE = "animescore_oauth"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def oauth_config():
    values = {key: os.getenv("BGM_" + key.upper(), "").strip() for key in ("client_id", "client_secret", "redirect_uri")}
    try:
        url = urlparse(values["redirect_uri"])
    except ValueError:
        return {**values, "enabled": False, "origin": None, "secure": True}
    valid_url = (url.scheme == "https" or (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}))
    values["enabled"] = bool(all(values.values()) and valid_url and url.netloc and not url.username and not url.password
                             and not url.query and not url.fragment and url.path == "/api/v1/auth/bangumi/callback")
    values["origin"] = f"{url.scheme}://{url.netloc}" if values["enabled"] else None
    values["secure"] = url.scheme == "https"
    return values


class OAuthLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and record.args[2].startswith("/api/v1/auth/bangumi/callback"):
            values = list(record.args)
            values[2] = values[2].split("?", 1)[0]
            record.args = tuple(values)
        return True


class Profile(BaseModel):
    id: int = Field(gt=0, strict=True)
    username: str = Field(min_length=1, max_length=100)
    nickname: str = Field(default="", max_length=200)


def initial_admin(profile):
    for value in os.getenv("BGM_ADMIN_IDS", "").split(","):
        identifier = value.strip()
        if "://" in identifier:
            try:
                url = urlparse(identifier)
                if (url.scheme not in {"http", "https"} or url.hostname not in {"bgm.tv", "bangumi.tv", "chii.in"}
                        or url.username or url.password or url.port or url.query or url.fragment):
                    continue
                parts = url.path.rstrip("/").split("/")
                if len(parts) != 3 or parts[:2] != ["", "user"]:
                    continue
                identifier = parts[2]
            except ValueError:
                continue
        if not identifier:
            continue
        if identifier.isascii() and identifier.isdigit():
            if identifier == str(profile.id):
                return True
        elif identifier == profile.username:
            return True
    return False


class AuthStore:
    def __init__(self, cache):
        self.cache = cache
        with cache.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT NOT NULL, nickname TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user', created_at REAL NOT NULL, last_login REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS session_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, return_to TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS role_audit (
                    id INTEGER PRIMARY KEY, actor TEXT NOT NULL, user_id INTEGER NOT NULL,
                    before_role TEXT NOT NULL, after_role TEXT NOT NULL, created_at REAL NOT NULL);
            """)

    def begin(self, return_to):
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.cache.connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires_at<?", (time.time(),))
            db.execute("INSERT INTO oauth_states VALUES (?, ?, ?, ?)",
                       (digest(state), digest(browser), return_to if return_to in {"/", "/admin"} else "/", time.time() + 600))
        return state, browser

    def consume(self, state, browser):
        if not state or not browser or max(len(state), len(browser)) > 200:
            raise ValueError("Invalid OAuth state")
        with self.cache.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT browser_hash, return_to, expires_at FROM oauth_states WHERE state_hash=?", (digest(state),)).fetchone()
            if not row or not secrets.compare_digest(row[0], digest(browser)) or row[2] < time.time():
                raise ValueError("Invalid OAuth state")
            db.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest(state),))
            return row[1]

    def login(self, raw_profile, previous_token=None, ttl=604800):
        profile = Profile.model_validate(raw_profile)
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        with self.cache.connect() as db:
            now = time.time()
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET username=excluded.username, nickname=excluded.nickname, last_login=excluded.last_login""",
                       (profile.id, profile.username, profile.nickname, "admin" if initial_admin(profile) else "user", now, now))
            db.execute("DELETE FROM sessions WHERE expires_at<? OR token_hash=?", (now, digest(previous_token or "")))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)", (digest(token), profile.id, csrf, now + ttl))
        return token

    def session(self, token):
        if not token or len(token) > 200:
            return None
        with self.cache.connect() as db:
            row = db.execute("""SELECT u.id, u.username, u.nickname, u.role, s.csrf FROM sessions s
                JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?""", (digest(token), time.time())).fetchone()
        return dict(zip(("id", "username", "nickname", "role", "csrf"), row)) if row else None

    def logout(self, token):
        with self.cache.connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token or ""),))

    def users(self, query="", offset=0):
        with self.cache.connect() as db:
            rows = db.execute("""SELECT id, username, nickname, role, last_login FROM users
                WHERE instr(lower(username), lower(?)) OR instr(nickname, ?) OR CAST(id AS TEXT)=?
                ORDER BY last_login DESC LIMIT 50 OFFSET ?""", (query, query, query, offset)).fetchall()
        return [dict(zip(("id", "username", "nickname", "role", "last_login"), row)) for row in rows]

    def set_role(self, user_id, role, actor):
        with self.cache.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise HTTPException(404, "该用户尚未登录本站")
            if row[0] == role:
                return
            if row[0] == "admin" and role != "admin" and db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
                raise HTTPException(409, "不能移除最后一位管理员")
            db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
            db.execute("INSERT INTO role_audit(actor,user_id,before_role,after_role,created_at) VALUES (?,?,?,?,?)",
                       (actor, user_id, row[0], role, time.time()))


def current_user(request: Request):
    return request.app.state.auth.session(request.cookies.get(SESSION_COOKIE))


def same_origin(request):
    origin = request.headers.get("origin")
    expected = oauth_config()["origin"] or str(request.base_url).rstrip("/")
    if origin and origin.rstrip("/") != expected:
        raise HTTPException(403, "仅接受同源请求")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "仅接受同源请求")


def check_csrf(request, user):
    same_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    if not supplied or not secrets.compare_digest(supplied.encode(), user["csrf"].encode()):
        raise HTTPException(403, "登录状态校验失败，请刷新页面")


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "请先使用 Bangumi 登录")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(request, user)
    return user


def authorize_admin(request: Request):
    same_origin(request)
    token = os.getenv("ANIMESCORE_ADMIN_TOKEN", "")
    authorization = request.headers.get("authorization", "")
    if authorization:
        supplied = authorization.removeprefix("Bearer ")
        if not token or not authorization.startswith("Bearer ") or not secrets.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(401, "管理员令牌无效")
        return "token"
    user = current_user(request)
    if user:
        if user["role"] != "admin":
            raise HTTPException(403, "需要管理员权限")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            check_csrf(request, user)
        return "bangumi"
    # Legacy local setup remains available only while OAuth is not configured.
    if not token and not oauth_config()["enabled"] and request.client and request.client.host in {"127.0.0.1", "::1"} and request.url.hostname in {"localhost", "127.0.0.1", "::1"}:
        return "local"
    raise HTTPException(401 if token or oauth_config()["enabled"] else 403, "请以管理员身份登录")
