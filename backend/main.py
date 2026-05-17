import os
import concurrent.futures
import json
import secrets
import time
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware


DEFAULT_OAUTH_CLIENT_FILE = Path(__file__).with_name("oauth_client.json")
TOKEN_DIR = Path(os.getenv("YTMUSIC_TOKEN_DIR", Path(__file__).with_name("oauth_tokens")))
SESSION_COOKIE_NAME = "ytwheel_session"
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
    return float(os.getenv("YTMUSIC_OAUTH_TIMEOUT", "15"))


def with_oauth_timeout(callback):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(callback)

    try:
        return future.result(timeout=oauth_timeout())
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def get_session_id(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

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


@lru_cache
def get_oauth_credentials():
    import requests
    from ytmusicapi import OAuthCredentials

    class TimeoutSession(requests.Session):
        def request(self, method, url, **kwargs):
            kwargs.setdefault("timeout", oauth_timeout())
            return super().request(method, url, **kwargs)

    oauth_client_file = Path(
        os.getenv("YTMUSIC_OAUTH_CLIENT_FILE", str(DEFAULT_OAUTH_CLIENT_FILE))
    )

    if not oauth_client_file.exists():
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
        raise HTTPException(
            status_code=503,
            detail="OAuth client file must include client_id and client_secret.",
        )

    return OAuthCredentials(
        client_id=client_id,
        client_secret=client_secret,
        session=TimeoutSession(),
    )


def get_user_ytmusic(request: Request):
    from ytmusicapi import YTMusic

    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_id:
        raise HTTPException(status_code=401, detail="Login required.")

    token_path = get_token_path(session_id)

    if not token_path.exists():
        raise HTTPException(status_code=401, detail="Login required.")

    return YTMusic(str(token_path), oauth_credentials=get_oauth_credentials())


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/status")
def auth_status(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    authenticated = bool(session_id and get_token_path(session_id).exists())

    return {"authenticated": authenticated}


@app.post("/auth/start")
def start_auth(request: Request, response: Response):
    session_id = get_session_id(request, response)
    credentials = get_oauth_credentials()

    try:
        auth_code = with_oauth_timeout(credentials.get_code)
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

    expires_at = int(time.time()) + int(auth_code.get("expires_in", 1800))

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
        "userCode": auth_code["user_code"],
        "verificationUrl": verification_url,
        "expiresIn": auth_code.get("expires_in", 1800),
        "interval": auth_code.get("interval", 5),
    }


@app.post("/auth/poll")
def poll_auth(request: Request, response: Response):
    session_id = get_session_id(request, response)
    pending_auth_code = pending_auth_codes.get(session_id)

    if not pending_auth_code:
        raise HTTPException(status_code=400, detail="No login is in progress.")

    if pending_auth_code["expires_at"] <= int(time.time()):
        pending_auth_codes.pop(session_id, None)
        raise HTTPException(status_code=400, detail="Login code expired.")

    try:
        token = with_oauth_timeout(
            lambda: get_oauth_credentials().token_from_code(pending_auth_code["device_code"])
        )
    except concurrent.futures.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Google OAuth did not respond before the timeout.",
        )
    except Exception as error:
        error_message = str(error).lower()

        if "authorization_pending" in error_message or "not yet" in error_message:
            return Response(status_code=status.HTTP_202_ACCEPTED)

        if "slow_down" in error_message:
            return Response(status_code=status.HTTP_202_ACCEPTED)

        if "expired" in error_message or "denied" in error_message:
            pending_auth_codes.pop(session_id, None)
            raise HTTPException(status_code=400, detail="Login was not approved in time.")

        raise HTTPException(status_code=502, detail=f"OAuth login failed: {error}")

    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))

    with get_token_path(session_id).open("w", encoding="utf-8") as file:
        json.dump(token, file, indent=2)

    pending_auth_codes.pop(session_id, None)

    return {"authenticated": True}


@app.post("/auth/logout")
def logout(request: Request, response: Response):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

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
