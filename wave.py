import sys
import urllib.request
import urllib.parse
import json
import os
import subprocess
import re
import time
from pathlib import Path

import requests
from mutagen.mp4 import MP4, MP4Cover

USERNAME = os.environ["USERNAME"]
API_KEY = os.environ["API_KEY"]

MUSIC_DIR = "/music"
ARCHIVE_FILE = f"{MUSIC_DIR}/archive.txt"

TAGR_URL = os.environ.get("TAGR_URL", "http://tagr:3000")
TAGR_FOLDER_PATH = "/music/MyWave"
TAGR_LOGIN_FILE = "/run/secrets/tagr_login"
TAGR_PASSWORD_FILE = "/run/secrets/tagr_password"

def sanitize_filename(value: str) -> str:
    if not value:
        return "Unknown"
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip().strip(".")
    return value[:120] or "Unknown"


def get_lastfm_album(artist_name: str, track_name: str) -> str | None:
    """Best-effort: реальный альбом трека, если Last.fm его знает."""
    try:
        url = (
            f"http://ws.audioscrobbler.com/2.0/"
            f"?method=track.getInfo"
            f"&artist={urllib.parse.quote(artist_name)}"
            f"&track={urllib.parse.quote(track_name)}"
            f"&api_key={API_KEY}"
            f"&autocorrect=1"
            f"&format=json"
        )
        with urllib.request.urlopen(url, timeout=10) as req:
            data = json.loads(req.read())
        return data.get("track", {}).get("album", {}).get("title")
    except Exception:
        return None


def embed_m4a_metadata(path, artist, title, album=None, cover_path=None) -> bool:
    path = Path(path)
    if not path.exists():
        print(f"Файл не найден для тегирования: {path}")
        return False

    try:
        audio = MP4(str(path))
        if audio.tags is None:
            audio.add_tags()

        audio.tags["\xa9nam"] = [title]
        audio.tags["\xa9ART"] = [artist]
        if album:
            audio.tags["\xa9alb"] = [album]
            audio.tags["aART"] = [artist]

        if cover_path:
            cover_path = Path(cover_path)
            if cover_path.exists():
                data = cover_path.read_bytes()
                if data:
                    fmt = MP4Cover.FORMAT_PNG if data.startswith(b"\x89PNG") else MP4Cover.FORMAT_JPEG
                    audio.tags["covr"] = [MP4Cover(data, imageformat=fmt)]

        audio.save()
        return True
    except Exception as e:
        print(f"Ошибка при записи тегов: {e}")
        return False


class TagrClient:
    """Тонкий клиент к Tagr: логин через NextAuth + запуск скана + bulk MusicBrainz cover-fetch."""
    BASE_PATH = "/tags"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/") + self.BASE_PATH
        self.session = requests.Session()

    def login(self, username: str, password: str) -> None:
        csrf = self.session.get(f"{self.base_url}/api/auth/csrf", timeout=10)
        csrf.raise_for_status()
        csrf_token = csrf.json().get("csrfToken")
        if not csrf_token:
            raise RuntimeError("Не получили csrfToken от Tagr")

        self.session.post(
            f"{self.base_url}/api/auth/callback/credentials",
            data={
                "csrfToken": csrf_token,
                "username": username,
                "password": password,
                "callbackUrl": self.base_url,
                "json": "true",
            },
            headers={"Accept": "application/json"},
            timeout=10,
        )

        check = self.session.get(f"{self.base_url}/api/auth/session", timeout=10)
        session_data = check.json() if check.content else {}
        if not session_data.get("user"):
            raise RuntimeError(
                "Логин в Tagr не подтвердился (сессия пустая). "
                "Проверьте логин/пароль в /run/secrets/tagr_*; если верны — "
                "сверьте реальный csrf/callback хендшейк curl'ом, детали NextAuth "
                "могли отличаться от предположенных здесь."
            )

    def start_scan(self, mode: str = "quick") -> str:
        resp = self.session.post(f"{self.base_url}/api/scan/start", json={"mode": mode}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Не удалось запустить скан: {data.get('error')}")
        return data["job"]["id"]

    def wait_for_scan(self, job_id: str, timeout: int = 600, poll_interval: int = 5) -> None:
        started = time.time()
        while time.time() - started < timeout:
            resp = self.session.get(f"{self.base_url}/api/scan/status/{job_id}", timeout=10)
            resp.raise_for_status()
            job = resp.json()["job"]
            if job["status"] == "completed":
                return
            if job["status"] == "failed":
                raise RuntimeError(f"Скан Tagr упал: {job.get('error')}")
            time.sleep(poll_interval)
        raise TimeoutError("Скан Tagr не завершился за отведённое время")

    def fetch_covers_for_folder(self, folder_path: str) -> list[dict]:
        resp = self.session.post(
            f"{self.base_url}/api/songs/bulk/musicbrainz/fetch-cover",
            json={"target": {"mode": "all-in-context", "context": {"type": "folder", "folderPath": folder_path}}},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        results = []
        for line in resp.iter_lines():
            if not line:
                continue
            event = json.loads(line)
            if event.get("type") == "result":
                results.append(event["result"])
            elif event.get("type") == "error":
                print(f"Tagr сообщил об ошибке в потоке: {event['error']}")
        return results


print("Запрашиваем историю прослушиваний...")

url = (
    f"http://ws.audioscrobbler.com/2.0/"
    f"?method=user.gettoptracks&user={USERNAME}&api_key={API_KEY}"
    f"&period=7day&limit=10&format=json"
)

downloaded_anything = False

try:
    req = urllib.request.urlopen(url)
    top_tracks = json.loads(req.read())["toptracks"]["track"]

    for t in top_tracks:
        artist = urllib.parse.quote(t["artist"]["name"])
        track = urllib.parse.quote(t["name"])

        sim_url = (
            f"http://ws.audioscrobbler.com/2.0/"
            f"?method=track.getsimilar&artist={artist}&track={track}"
            f"&api_key={API_KEY}&limit=3&format=json"
        )
        sim_req = urllib.request.urlopen(sim_url)
        sim_data = json.loads(sim_req.read())
        sim_tracks = sim_data.get("similartracks", {}).get("track", [])
        if isinstance(sim_tracks, dict):
            sim_tracks = [sim_tracks]

        for st in sim_tracks:
            query = "unknown"
            try:
                artist_name = st["artist"]["name"]
                track_name = st["name"]
                query = f"{artist_name} - {track_name}"
                print(f"\nНайдена рекомендация: {query}")

                base_name = f"{sanitize_filename(artist_name)} - {sanitize_filename(track_name)}"
                output_template = f"{MUSIC_DIR}/{base_name}.%(ext)s"
                audio_path = Path(MUSIC_DIR) / f"{base_name}.m4a"
                cover_path = Path(MUSIC_DIR) / f"{base_name}.jpg"

                result = subprocess.run([
                    sys.executable, "-m", "yt_dlp", 
                    f"ytsearch1:{query}",
                    "--extractor-args", "youtube:player_client=web_embedded",
                    "-x", "--audio-format", "m4a", "--audio-quality", "0",
                    "--output", output_template,
                    "--download-archive", ARCHIVE_FILE,
                    "--no-playlist",
                    "--write-thumbnail", "--convert-thumbnails", "jpg",
                ])

                if result.returncode != 0:
                    print(f"❌ Ошибка скачивания: {query}")
                    continue
                if not audio_path.exists():
                    print(f"⚠️ Аудиофайл не найден: {audio_path}")
                    continue

                album = get_lastfm_album(artist_name, track_name)
                embed_m4a_metadata(
                    path=audio_path, artist=artist_name, title=track_name,
                    album=album, cover_path=cover_path if cover_path.exists() else None,
                )
                downloaded_anything = True
                print(f"✓ Готово: {query}" + (f" (альбом: {album})" if album else " (альбом неизвестен)"))

            except Exception as e:
                print(f"❌ Ошибка обработки '{query}': {type(e).__name__}: {e}")
            finally:
                if cover_path.exists():
                    try:
                        cover_path.unlink()
                    except Exception:
                        pass

except Exception as e:
    print("Ошибка при запросе к Last.fm:", e)

if downloaded_anything:
    try:
        tagr_login = Path(TAGR_LOGIN_FILE).read_text().strip()
        tagr_password = Path(TAGR_PASSWORD_FILE).read_text().strip()

        client = TagrClient(TAGR_URL)
        client.login(tagr_login, tagr_password)

        print("\nЗапускаем скан библиотеки в Tagr...")
        job_id = client.start_scan(mode="quick")
        client.wait_for_scan(job_id)

        print("Скан завершён, запрашиваем обложки через MusicBrainz для MyWave...")
        results = client.fetch_covers_for_folder(TAGR_FOLDER_PATH)
        ok = sum(1 for r in results if r.get("ok"))
        print(f"Обложки: успешно {ok} из {len(results)}")
        for r in results:
            if not r.get("ok"):
                print(f"  без обложки (song {r['songId']}): {r.get('error')}")

    except Exception as e:
        print(f"Автоматизация Tagr не выполнена: {e}")
