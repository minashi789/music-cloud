import urllib.request
import urllib.parse
import json
import os
import subprocess

USERNAME = os.environ["USERNAME"]
API_KEY = os.environ["API_KEY"]

MUSIC_DIR = "/music"
ARCHIVE_FILE = "/music/archive.txt"

print("Запрашиваем историю прослушиваний...")

url = (
    f"http://ws.audioscrobbler.com/2.0/"
    f"?method=user.gettoptracks"
    f"&user={USERNAME}"
    f"&api_key={API_KEY}"
    f"&period=7day"
    f"&limit=10"
    f"&format=json"
)

try:
    req = urllib.request.urlopen(url)
    top_tracks = json.loads(req.read())["toptracks"]["track"]

    for t in top_tracks:
        artist = urllib.parse.quote(t["artist"]["name"])
        track = urllib.parse.quote(t["name"])

        sim_url = (
            f"http://ws.audioscrobbler.com/2.0/"
            f"?method=track.getsimilar"
            f"&artist={artist}"
            f"&track={track}"
            f"&api_key={API_KEY}"
            f"&limit=3"
            f"&format=json"
        )

        sim_req = urllib.request.urlopen(sim_url)
        sim_tracks = json.loads(sim_req.read())["similartracks"]["track"]

        for st in sim_tracks:
            artist_name = st["artist"]["name"]
            track_name = st["name"]
            query = f"{artist_name} - {track_name}"

            print(f"Найдена рекомендация: {query}")

            result = subprocess.run([
                "yt-dlp",
                f"ytsearch1:{query}",
                "--extractor-args",
                "youtube:player_client=web_embedded",
                "-x",
                "--audio-format",
                "m4a",
                "--audio-quality",
                "0",
                "--output",
                f"{MUSIC_DIR}/{query}.%(ext)s",
                "--download-archive",
                ARCHIVE_FILE,
                "--no-playlist"
            ])

            if result.returncode != 0:
                print(f"Ошибка скачивания: {query}")
            else:
                print(f"Скачивание завершено: {query}")

except Exception as e:
    print("Ошибка при запросе к Last.fm:", e)
