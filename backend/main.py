import os
import concurrent.futures
import json
import logging
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware


logger = logging.getLogger("yt-wheel")

DEFAULT_OAUTH_CLIENT_FILE = Path(__file__).with_name("oauth_client.json")
TOKEN_DIR = Path(os.getenv("YTMUSIC_TOKEN_DIR", Path(__file__).with_name("oauth_tokens")))
SESSION_COOKIE_NAME = "ytwheel_session"
SESSION_HEADER_NAME = "x-ytwheel-session"
GOOGLE_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_OAUTH_SCOPE = "https://www.googleapis.com/auth/youtube"
pending_auth_codes = {}

app = FastAPI()

frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cookie_secure():
    return os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"


def cookie_samesite():
    return os.getenv("SESSION_COOKIE_SAMESITE", "lax")


def oauth_timeout():
    return float(os.getenv("YTMUSIC_OAUTH_TIMEOUT", "30"))


def auth_code_grace_seconds():
    return int(os.getenv("YTMUSIC_AUTH_CODE_GRACE_SECONDS", "120"))


def with_oauth_timeout(callback):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(callback)

    try:
        return future.result(timeout=oauth_timeout())
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def post_google_oauth(url: str, data: dict):
    return requests.post(url, data=data, timeout=oauth_timeout())


def normalize_session_id(session_id: str | None):
    if session_id and re.fullmatch(r"[A-Za-z0-9_-]{20,160}", session_id):
        return session_id

    return None


def get_request_session_id(request: Request):
    return normalize_session_id(
        request.cookies.get(SESSION_COOKIE_NAME)
        or request.headers.get(SESSION_HEADER_NAME)
    )


def get_or_create_session_id(request: Request, response: Response):
    session_id = get_request_session_id(request)

    if session_id:
        return session_id

    session_id = secrets.token_urlsafe(32)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        secure=cookie_secure(),
        samesite=cookie_samesite(),
        max_age=60 * 60 * 24 * 30,
    )
    return session_id


def get_token_path(session_id: str):
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    return TOKEN_DIR / f"{session_id}.json"


def get_oauth_client_path():
    return Path(os.getenv("YTMUSIC_OAUTH_CLIENT_FILE", str(DEFAULT_OAUTH_CLIENT_FILE)))


def inspect_oauth_client_file():
    oauth_client_file = get_oauth_client_path()
    result = {
        "envName": "YTMUSIC_OAUTH_CLIENT_FILE",
        "configuredPath": str(oauth_client_file),
        "exists": oauth_client_file.exists(),
        "isFile": oauth_client_file.is_file(),
        "hasClientId": False,
        "hasClientSecret": False,
        "jsonShape": None,
        "error": None,
    }

    if not result["exists"] or not result["isFile"]:
        return result

    try:
        with oauth_client_file.open("r", encoding="utf-8") as file:
            oauth_client = json.load(file)

        if "installed" in oauth_client:
            result["jsonShape"] = "installed"
            client_config = oauth_client["installed"]
        elif "web" in oauth_client:
            result["jsonShape"] = "web"
            client_config = oauth_client["web"]
        else:
            result["jsonShape"] = "root"
            client_config = oauth_client

        result["hasClientId"] = bool(client_config.get("client_id"))
        result["hasClientSecret"] = bool(client_config.get("client_secret"))
    except Exception as error:
        result["error"] = str(error)

    return result


@lru_cache
def get_oauth_client_config():
    oauth_client_file = get_oauth_client_path()

    if not oauth_client_file.exists():
        logger.error(
            "OAuth client file was not found. YTMUSIC_OAUTH_CLIENT_FILE=%s",
            oauth_client_file,
        )
        raise HTTPException(
            status_code=503,
            detail=f"OAuth client file was not found at {oauth_client_file}",
        )

    with oauth_client_file.open("r", encoding="utf-8") as file:
        oauth_client = json.load(file)

    client_config = oauth_client.get("installed") or oauth_client.get("web") or oauth_client
    client_id = client_config.get("client_id")
    client_secret = client_config.get("client_secret")

    if not client_id or not client_secret:
        logger.error(
            "OAuth client file is missing client_id or client_secret. "
            "YTMUSIC_OAUTH_CLIENT_FILE=%s",
            oauth_client_file,
        )
        raise HTTPException(
            status_code=503,
            detail="OAuth client file must include client_id and client_secret.",
        )

    return {"client_id": client_id, "client_secret": client_secret}


@lru_cache
def get_oauth_credentials():
    from ytmusicapi import OAuthCredentials

    class TimeoutSession(requests.Session):
        def request(self, method, url, **kwargs):
            kwargs.setdefault("timeout", oauth_timeout())
            return super().request(method, url, **kwargs)

    client_config = get_oauth_client_config()

    return OAuthCredentials(
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        session=TimeoutSession(),
    )


def get_user_ytmusic(request: Request):
    from ytmusicapi import YTMusic

    session_id = get_request_session_id(request)

    if not session_id:
        raise HTTPException(status_code=401, detail="Login required.")

    token_path = get_token_path(session_id)

    if not token_path.exists():
        raise HTTPException(status_code=401, detail="Login required.")

    return YTMusic(str(token_path), oauth_credentials=get_oauth_credentials())


@app.on_event("startup")
def log_oauth_setup():
    diagnostics = inspect_oauth_client_file()
    logger.warning("OAuth client diagnostics at startup: %s", diagnostics)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/debug")
def auth_debug():
    return inspect_oauth_client_file()


@app.get("/auth/status")
def auth_status(request: Request):
    session_id = get_request_session_id(request)
    authenticated = bool(session_id and get_token_path(session_id).exists())

    return {"authenticated": authenticated}


@app.post("/auth/start")
def start_auth(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    client_config = get_oauth_client_config()

    try:
        google_response = with_oauth_timeout(
            lambda: post_google_oauth(
                GOOGLE_DEVICE_CODE_URL,
                {
                    "client_id": client_config["client_id"],
                    "scope": YOUTUBE_OAUTH_SCOPE,
                },
            )
        )
    except concurrent.futures.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Google OAuth did not respond before the timeout.",
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Google OAuth: {error}",
        )

    auth_code = google_response.json()

    if not google_response.ok:
        raise HTTPException(
            status_code=502,
            detail=auth_code.get("error_description")
            or auth_code.get("error")
            or "Could not start Google OAuth.",
        )

    expires_at = (
        int(time.time())
        + int(auth_code.get("expires_in", 1800))
        + auth_code_grace_seconds()
    )

    pending_auth_codes[session_id] = {
        "device_code": auth_code["device_code"],
        "expires_at": expires_at,
    }

    verification_url = (
        auth_code.get("verification_url")
        or auth_code.get("verification_uri")
        or "https://www.google.com/device"
    )

    return {
        "sessionId": session_id,
        "userCode": auth_code["user_code"],
        "verificationUrl": verification_url,
        "expiresIn": auth_code.get("expires_in", 1800),
        "interval": auth_code.get("interval", 5),
    }


@app.post("/auth/poll")
def poll_auth(request: Request, response: Response):
    session_id = get_or_create_session_id(request, response)
    pending_auth_code = pending_auth_codes.get(session_id)
    client_config = get_oauth_client_config()

    if not pending_auth_code:
        raise HTTPException(status_code=400, detail="No login is in progress.")

    if pending_auth_code["expires_at"] <= int(time.time()):
        pending_auth_codes.pop(session_id, None)
        raise HTTPException(status_code=400, detail="Login code expired.")

    try:
        token_response = with_oauth_timeout(
            lambda: post_google_oauth(
                GOOGLE_TOKEN_URL,
                {
                    "client_id": client_config["client_id"],
                    "client_secret": client_config["client_secret"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": pending_auth_code["device_code"],
                },
            )
        )
    except concurrent.futures.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Google OAuth did not respond before the timeout.",
        )
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"OAuth login failed: {error}")

    token = token_response.json()

    if not token_response.ok:
        error_message = str(token.get("error", "")).lower()

        if error_message == "authorization_pending":
            return Response(status_code=status.HTTP_202_ACCEPTED)

        if error_message == "slow_down":
            return Response(status_code=status.HTTP_202_ACCEPTED)

        if error_message in {"expired_token", "access_denied"}:
            pending_auth_codes.pop(session_id, None)
            raise HTTPException(status_code=400, detail="Login was not approved in time.")

        raise HTTPException(
            status_code=502,
            detail=token.get("error_description")
            or token.get("error")
            or "OAuth login failed.",
        )

    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))

    with get_token_path(session_id).open("w", encoding="utf-8") as file:
        json.dump(token, file, indent=2)

    pending_auth_codes.pop(session_id, None)

    return {"authenticated": True}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    session_id = get_request_session_id(request)

    if session_id:
        token_path = get_token_path(session_id)
        token_path.unlink(missing_ok=True)
        pending_auth_codes.pop(session_id, None)

    response.delete_cookie(
        SESSION_COOKIE_NAME,
        secure=cookie_secure(),
        httponly=True,
        samesite=cookie_samesite(),
    )

    return {"authenticated": False}


@app.get("/albums")
def get_albums(request: Request):
    yt = get_user_ytmusic(request)

    raw_albums = yt.get_library_albums(limit=1000)

    albums = []

    for album in raw_albums:

        title = album.get("title", "Unknown Album")

        # artists might not exist
        artist = "Unknown Artist"

        if "artists" in album and len(album["artists"]) > 0:
            artist = album["artists"][0].get("name", "Unknown Artist")

        # thumbnails might not exist
        thumbnail = ""

        if "thumbnails" in album and len(album["thumbnails"]) > 0:
            thumbnail = album["thumbnails"][-1].get("url", "")

        # browseId might not exist
        browse_id = album.get("browseId", "")

        albums.append({
            "title": title,
            "artist": artist,
            "thumbnail": thumbnail,
            "browseId": browse_id
        })

    return {"albums": albums}
