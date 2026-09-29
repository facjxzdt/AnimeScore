"""OAuth redirects never expose Bangumi access tokens to the browser."""

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse

from services.auth import SESSION_COOKIE, STATE_COOKIE, current_user, oauth_config, require_user

router = APIRouter()


@router.get("/me")
def me(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    user = current_user(request)
    return {"user": {key: value for key, value in user.items() if key != "csrf"} if user else None,
            "csrf_token": user["csrf"] if user else None, "login_enabled": oauth_config()["enabled"],
            "review_enabled": request.app.state.contributions.reviewer.enabled,
            "quota": request.app.state.contributions.quota(user["id"]) if user else None}


@router.get("/bangumi/login")
def login(request: Request, return_to: str = Query("/", max_length=20)):
    config = oauth_config()
    if not config["enabled"]:
        raise HTTPException(503, "Bangumi 登录尚未配置")
    state, browser = request.app.state.auth.begin(return_to)
    response = RedirectResponse("https://bgm.tv/oauth/authorize?" + urlencode({
        "client_id": config["client_id"], "response_type": "code", "redirect_uri": config["redirect_uri"], "state": state}), status_code=302)
    response.set_cookie(STATE_COOKIE, browser, max_age=600, httponly=True, secure=config["secure"], samesite="lax", path="/api/v1/auth/bangumi")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/bangumi/callback")
async def callback(request: Request, state: str = Query("", max_length=200), code: str = Query("", max_length=512), error: str = Query("", max_length=200)):
    config = oauth_config()
    if not config["enabled"]:
        raise HTTPException(503, "Bangumi 登录尚未配置")
    try:
        return_to = request.app.state.auth.consume(state, request.cookies.get(STATE_COOKIE))
    except ValueError:
        raise HTTPException(400, "登录验证已过期或与当前浏览器不符，请重新登录") from None
    if error or not code:
        response = RedirectResponse("/?auth_error=cancelled", status_code=303)
    else:
        try:
            client = request.app.state.ratings.client
            token_response = await client.post("https://bgm.tv/oauth/access_token", data={
                "grant_type": "authorization_code", "client_id": config["client_id"], "client_secret": config["client_secret"],
                "code": code, "redirect_uri": config["redirect_uri"]}, follow_redirects=False, timeout=15)
            token_response.raise_for_status()
            token = token_response.json()
            profile_response = await client.get("https://api.bgm.tv/v0/me", headers={"Authorization": "Bearer " + token["access_token"]}, follow_redirects=False, timeout=15)
            profile_response.raise_for_status()
            profile = profile_response.json()
            if str(profile["id"]) != str(token["user_id"]):
                raise ValueError("Bangumi identity mismatch")
            ttl = min(604800, max(60, int(token["expires_in"])))
            session = request.app.state.auth.login(profile, request.cookies.get(SESSION_COOKIE), ttl)
            response = RedirectResponse(return_to, status_code=303)
            response.set_cookie(SESSION_COOKIE, session, max_age=ttl, httponly=True, secure=config["secure"], samesite="lax")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            response = RedirectResponse("/?auth_error=unavailable", status_code=303)
    response.delete_cookie(STATE_COOKIE, path="/api/v1/auth/bangumi")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(require_user)):
    request.app.state.auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
