from ytmusicapi import YTMusic

yt = YTMusic(auth="headers_auth.json")

albums = yt.get_library_albums(limit=5)

for album in albums:
    print(album["title"])