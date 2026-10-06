"""YouTube InnerTube 経由の字幕取得（Cloudflare Worker が 429 のときのサーバー側フォールバック）。"""

from __future__ import annotations

import http.cookiejar
import json
import logging
import re
import ssl
import threading
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener, urlopen as std_urlopen

from urllib.parse import unquote

from toolbox.config import DATA_DIR

_VIDEO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_VIDEO_ID_FROM_URL_RE = re.compile(
    r"(?:v=|vi=|/)([0-9A-Za-z_-]{11})(?=$|[^0-9A-Za-z_-])",
    re.IGNORECASE,
)


def extract_video_id(url: str) -> str:
    if not url or not str(url).strip():
        raise ValueError("YouTube URL または動画 ID を入力してください。")
    raw = unquote(str(url).strip()).split("#", 1)[0]
    if _VIDEO_ID_PATTERN.fullmatch(raw):
        return raw
    match = _VIDEO_ID_FROM_URL_RE.search(raw)
    if match and _VIDEO_ID_PATTERN.fullmatch(match.group(1)):
        return match.group(1)
    raise ValueError("有効な YouTube URL または 11 桁の動画 ID を入力してください。")

logger = logging.getLogger(__name__)

WORKER_PROXY_URL = "https://vibe-speak-proxy.kishineseiichi.workers.dev/"
VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

INNERTUBE_PLAYER_URL = "https://www.youtube.com/youtubei/v1/player?prettyPrint=false"
DEFAULT_LANGUAGES = ("en", "ja")
CACHE_DIR = DATA_DIR / "cnn10_youtube_transcripts"
# 本番 Render ではトップページより CNN10 チャンネル HTML の方が通る（一覧取得と同じ経路）。
YOUTUBE_WARMUP_URL = "https://www.youtube.com/@CNN10/videos"
CONSENT_COOKIE = "CONSENT=YES+; SOCS=CAI; PREF=hl=en&tz=UTC"
CHANNEL_UA = "Mozilla/5.0"

INNERTUBE_CLIENTS = (
    {
        "name": "ANDROID",
        "context": {"client": {"clientName": "ANDROID", "clientVersion": "20.10.38"}},
        "user_agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 14)",
    },
    {
        "name": "IOS",
        "context": {
            "client": {
                "clientName": "IOS",
                "clientVersion": "20.10.4",
                "deviceModel": "iPhone16,2",
            }
        },
        "user_agent": "com.google.ios.youtube/20.10.4 (iPhone16,2; U; CPU iOS 18_3_2 like Mac OS X;)",
    },
)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_P_TAG_RE = re.compile(r'<p\s+t="(\d+)"\s+d="(\d+)"[^>]*>([\s\S]*?)</p>')
_S_TAG_RE = re.compile(r"<s[^>]*>([^<]*)</s>")
_TEXT_TAG_RE = re.compile(r'<text start="([^"]*)" dur="([^"]*)">([^<]*)</text>')
_TAG_RE = re.compile(r"<[^>]+>")
_VISITOR_RE = re.compile(r'"visitorData":"([^"]+)"')

_opener_lock = threading.Lock()
_opener = None
_session_warmed = False


class TranscriptRateLimited(Exception):
    """YouTube がこの IP からの字幕リクエストを制限している。"""


class TranscriptNotFound(Exception):
    """対象言語の字幕が見つからない。"""


def _build_opener(*, unverified: bool = False):
    jar = http.cookiejar.CookieJar()
    handlers = [HTTPCookieProcessor(jar)]
    if unverified:
        handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
    return build_opener(*handlers)


def _get_opener():
    global _opener
    if _opener is None:
        with _opener_lock:
            if _opener is None:
                _opener = _build_opener()
    return _opener


def _simple_urlopen(request: Request, timeout: int = 12):
    """CNN10 一覧と同じく Cookie なしの素の GET。"""
    try:
        return std_urlopen(request, timeout=timeout)
    except ssl.SSLError:
        pass
    except URLError as exc:
        if not isinstance(exc.reason, ssl.SSLError):
            raise
    return std_urlopen(request, timeout=timeout, context=ssl._create_unverified_context())


def _urlopen(request: Request, timeout: int = 12):
    global _opener
    opener = _get_opener()
    try:
        return opener.open(request, timeout=timeout)
    except ssl.SSLError:
        pass
    except URLError as exc:
        if not isinstance(exc.reason, ssl.SSLError):
            raise
    with _opener_lock:
        _opener = _build_opener(unverified=True)
    return _opener.open(request, timeout=timeout)


def _reset_youtube_session() -> None:
    global _opener, _session_warmed
    with _opener_lock:
        _opener = None
        _session_warmed = False


def _warmup_youtube_session() -> None:
    """CNN10 一覧と同じチャンネル HTML で VISITOR Cookie を取る。データセンターではトップページだけだと字幕が空になる。"""
    global _session_warmed
    if _session_warmed:
        return
    request = Request(
        YOUTUBE_WARMUP_URL,
        headers={
            "User-Agent": CHANNEL_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": CONSENT_COOKIE,
        },
    )
    try:
        with _urlopen(request, timeout=12) as response:
            html = response.read().decode("utf-8", errors="replace")
        if "ytInitialData" in html or "ytcfg.set" in html:
            _session_warmed = True
            logger.info("youtube session warmed via CNN10 channel page (%d bytes)", len(html))
        else:
            logger.info("youtube warmup html had no ytInitialData (%d bytes)", len(html))
    except (OSError, URLError, HTTPError) as exc:
        logger.info("youtube session warmup failed: %s", exc)


def _round_sec(value: float) -> float:
    return round(float(value) * 1000) / 1000


def _lang_matches(candidate: str, preferred: str) -> bool:
    c = (candidate or "").lower()
    p = (preferred or "").lower()
    return c == p or c.startswith(f"{p}-")


def _parse_timedtext_xml(xml: str) -> list[dict]:
    snippets: list[dict] = []
    for match in _P_TAG_RE.finditer(xml or ""):
        start_ms = int(match.group(1))
        dur_ms = int(match.group(2))
        inner = match.group(3)
        parts = _S_TAG_RE.findall(inner)
        text = "".join(parts) if parts else _TAG_RE.sub("", inner)
        text = unescape(text).strip()
        if not text:
            continue
        snippets.append(
            {
                "start": _round_sec(start_ms / 1000),
                "duration": _round_sec(max(dur_ms / 1000, 0.1)),
                "text": text,
            }
        )
    if snippets:
        return snippets

    for match in _TEXT_TAG_RE.finditer(xml or ""):
        text = unescape(match.group(3)).strip()
        if not text:
            continue
        snippets.append(
            {
                "start": _round_sec(float(match.group(1))),
                "duration": _round_sec(max(float(match.group(2)), 0.1)),
                "text": text,
            }
        )
    return snippets


def _select_track(tracks: list[dict], languages: tuple[str, ...]) -> dict | None:
    if not tracks:
        return None
    manual = [t for t in tracks if t.get("kind") != "asr"]
    auto = [t for t in tracks if t.get("kind") == "asr"]
    for pool in (manual, auto):
        for lang in languages:
            for track in pool:
                if _lang_matches(str(track.get("languageCode") or ""), lang):
                    return track
    return (manual or auto or [None])[0]


def _cache_path(video_id: str) -> Path:
    return CACHE_DIR / f"{video_id}.json"


def _read_cache(video_id: str) -> dict | None:
    path = _cache_path(video_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("snippets"):
        return None
    return data


def _write_cache(video_id: str, payload: dict) -> None:
    if not payload.get("snippets"):
        return
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(video_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("failed to cache youtube transcript for %s", video_id)


def _public_tracks(tracks: list[dict]) -> list[dict]:
    out = []
    for track in tracks or []:
        base_url = track.get("baseUrl")
        if not base_url:
            continue
        out.append(
            {
                "languageCode": str(track.get("languageCode") or ""),
                "kind": str(track.get("kind") or ""),
                "baseUrl": str(base_url),
            }
        )
    return out


def _fetch_channel_visitor_data() -> str:
    """CNN10 一覧と同じ単純 GET で visitorData を取る。"""
    request = Request(
        YOUTUBE_WARMUP_URL,
        headers={
            "User-Agent": CHANNEL_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": CONSENT_COOKIE,
        },
    )
    try:
        with _simple_urlopen(request, timeout=12) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (OSError, URLError, HTTPError) as exc:
        logger.info("channel visitor fetch failed: %s", exc)
        return ""
    match = _VISITOR_RE.search(html)
    visitor = match.group(1) if match else ""
    logger.info(
        "channel html len=%d visitor=%s ytInitialData=%s",
        len(html),
        bool(visitor),
        "ytInitialData" in html,
    )
    return visitor


def _fetch_caption_tracks(video_id: str, client: dict, visitor_data: str = "") -> list[dict]:
    context = json.loads(json.dumps(client["context"]))
    if visitor_data:
        context.setdefault("client", {})["visitorData"] = visitor_data
    payload = {"context": context, "videoId": video_id}
    request = Request(
        INNERTUBE_PLAYER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": client["user_agent"],
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
            "Cookie": CONSENT_COOKIE,
        },
        method="POST",
    )
    try:
        with _urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            raise TranscriptRateLimited("YouTube へのリクエストが制限されています。") from exc
        logger.info("innertube %s HTTP %s for %s", client["name"], exc.code, video_id)
        return []
    except (OSError, URLError, json.JSONDecodeError) as exc:
        logger.info("innertube %s failed for %s: %s", client["name"], video_id, exc)
        return []

    tracks = (
        (data.get("captions") or {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks")
        or []
    )
    return tracks if isinstance(tracks, list) else []


def _extract_json_object(html: str, marker: str) -> dict | None:
    start = html.find(marker)
    if start < 0:
        return None
    start = html.find("{", start)
    if start < 0:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(html[start:])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _tracks_from_player_response(data: dict | None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    tracks = (
        (data.get("captions") or {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks")
        or []
    )
    return tracks if isinstance(tracks, list) else []


def _fetch_tracks_from_watch_page(video_id: str) -> list[dict]:
    """CNN10 一覧と同じく watch HTML は Render から通ることがある。"""
    headers = {
        "User-Agent": CHANNEL_UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": CONSENT_COOKIE,
        "Referer": YOUTUBE_WARMUP_URL,
    }
    watch_request = Request(
        f"https://www.youtube.com/watch?v={video_id}&hl=en",
        headers=headers,
    )
    try:
        with _simple_urlopen(watch_request, timeout=12) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (OSError, URLError, HTTPError) as exc:
        logger.info("watch html failed for %s: %s", video_id, exc)
        return []
    logger.info(
        "watch html %s len=%d player=%s recaptcha=%s",
        video_id,
        len(html),
        "ytInitialPlayerResponse" in html,
        "g-recaptcha" in html,
    )
    if "g-recaptcha" in html and "ytInitialPlayerResponse" not in html:
        logger.info("watch html recaptcha for %s", video_id)
        return []
    player = _extract_json_object(html, "ytInitialPlayerResponse")
    return _tracks_from_player_response(player)


def _fetch_timedtext(base_url: str) -> list[dict]:
    request = Request(
        base_url,
        headers={
            "User-Agent": BROWSER_UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Cookie": CONSENT_COOKIE,
            "Referer": "https://www.youtube.com/",
        },
    )
    try:
        with _urlopen(request, timeout=12) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        if exc.code == 429:
            raise TranscriptRateLimited("YouTube へのリクエストが制限されています。") from exc
        return []
    except (OSError, URLError):
        return []
    return _parse_timedtext_xml(body)


def _payload_from_tracks(
    tracks: list[dict],
    languages: tuple[str, ...],
    snippets: list[dict] | None = None,
) -> dict | None:
    caption_tracks = _public_tracks(tracks)
    selected = _select_track(caption_tracks, languages)
    if not selected:
        return None
    return {
        "language_code": str(selected.get("languageCode") or languages[0] or "en"),
        "is_generated": selected.get("kind") == "asr",
        "snippets": snippets or [],
        "caption_tracks": caption_tracks,
    }


def _is_safe_timedtext_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if host not in ("www.youtube.com", "youtube.com"):
        return False
    return "timedtext" in (parsed.path or "")


def fetch_timedtext_from_url(url: str) -> dict:
    """ブラウザが CORS で本文を取れないとき、署名付き timedtext URL をサーバー経由で取得する。"""
    if not _is_safe_timedtext_url(url):
        raise ValueError("timedtext URL が不正です。")
    snippets = _fetch_timedtext(url)
    if not snippets:
        raise TranscriptNotFound("日本語・英語の字幕が見つかりませんでした。")
    return {
        "language_code": "en",
        "is_generated": True,
        "snippets": snippets,
    }


def fetch_via_worker_relay(video_id: str) -> dict:
    """学校のネットワークが *.workers.dev を直接ブロックしているケース向けに、
    Render（同一オリジン）から Cloudflare Worker を代理で叩いて結果を返す。
    ブラウザは常に自分のドメインにしかアクセスしないので、Worker のドメインが
    フィルタされていても字幕データを受け取れる。
    """
    if not VIDEO_ID_RE.match(video_id or ""):
        raise ValueError("有効な 11 桁の YouTube 動画 ID を指定してください。")
    request = Request(
        f"{WORKER_PROXY_URL}?id={video_id}",
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with _urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body)
        except (OSError, json.JSONDecodeError, ValueError):
            data = {}
        message = str(data.get("error") or "字幕プロキシの呼び出しに失敗しました。")
        if exc.code == 429:
            raise TranscriptRateLimited(message) from exc
        if exc.code == 404:
            raise TranscriptNotFound(message) from exc
        raise RuntimeError(message) from exc
    except (OSError, URLError) as exc:
        raise RuntimeError(f"字幕プロキシに接続できませんでした: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("字幕プロキシのレスポンスを解析できませんでした。") from exc
    if not isinstance(data, dict):
        raise RuntimeError("字幕プロキシのレスポンス形式が不正です。")
    return data


def fetch_youtube_transcript(url_or_video_id: str, languages: tuple[str, ...] = DEFAULT_LANGUAGES) -> dict:
    """字幕本文を取得する。本文が空でもトラック URL があればブラウザ側フォールバック用に返す。"""
    video_id = extract_video_id(url_or_video_id)
    cached = _read_cache(video_id)
    if cached:
        return cached

    _warmup_youtube_session()
    visitor_data = _fetch_channel_visitor_data()

    last_rate_limited = False
    collected_tracks: list[dict] = []

    html_tracks = _fetch_tracks_from_watch_page(video_id)
    if html_tracks:
        collected_tracks = html_tracks
        selected = _select_track(_public_tracks(html_tracks), languages)
        if selected and selected.get("baseUrl"):
            try:
                snippets = _fetch_timedtext(str(selected["baseUrl"]))
            except TranscriptRateLimited:
                last_rate_limited = True
                snippets = []
            if snippets:
                payload = _payload_from_tracks(html_tracks, languages, snippets)
                if payload:
                    _write_cache(video_id, payload)
                    logger.info(
                        "youtube transcript fetched (%s, %s, %d snippets) via watch html",
                        video_id,
                        payload["language_code"],
                        len(snippets),
                    )
                    return payload

    for client in INNERTUBE_CLIENTS:
        try:
            tracks = _fetch_caption_tracks(video_id, client, visitor_data)
        except TranscriptRateLimited:
            last_rate_limited = True
            continue
        if not tracks:
            logger.info("innertube %s returned no caption tracks for %s", client["name"], video_id)
            continue
        logger.info("innertube %s returned %d caption tracks for %s", client["name"], len(tracks), video_id)
        collected_tracks = tracks
        selected = _select_track(_public_tracks(tracks), languages)
        if not selected or not selected.get("baseUrl"):
            continue
        try:
            snippets = _fetch_timedtext(str(selected["baseUrl"]))
        except TranscriptRateLimited:
            last_rate_limited = True
            continue
        if snippets:
            payload = _payload_from_tracks(tracks, languages, snippets)
            if payload:
                _write_cache(video_id, payload)
                logger.info(
                    "youtube transcript fetched (%s, %s, %d snippets) via %s",
                    video_id,
                    payload["language_code"],
                    len(snippets),
                    client["name"],
                )
                return payload

    if collected_tracks:
        payload = _payload_from_tracks(collected_tracks, languages, [])
        if payload:
            logger.info(
                "youtube caption tracks only (%s, %d tracks); browser will fetch timedtext",
                video_id,
                len(payload["caption_tracks"]),
            )
            return payload

    _reset_youtube_session()
    if last_rate_limited:
        raise TranscriptRateLimited("YouTube へのリクエストが制限されています。しばらく待ってから再試行してください。")
    raise TranscriptNotFound("日本語・英語の字幕が見つかりませんでした。")
