import os
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


DEFAULT_AUTH_FILE = Path(__file__).with_name("headers_auth.json")

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

@lru_cache
def get_ytmusic():
    from ytmusicapi import YTMusic

    auth_file = Path(os.getenv("YTMUSIC_AUTH_FILE", str(DEFAULT_AUTH_FILE)))

    if not auth_file.exists():
        raise HTTPException(
            status_code=503,
            detail=f"YouTube Music auth file was not found at {auth_file}",
        )

    return YTMusic(str(auth_file))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/albums")
def get_albums():
    yt = get_ytmusic()

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
