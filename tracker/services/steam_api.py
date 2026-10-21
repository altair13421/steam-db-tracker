"""Steam storefront API client (Django port of the CLI bot's store_api).

Uses the same public, no-API-key endpoints as the CLI bot:
  - https://store.steampowered.com/api/appdetails
  - https://api.steampowered.com/ISteamNews/GetNewsForApp/v2
  - https://api.steampowered.com/ISteamApps/GetAppList/v2

Throttled by default to STEAM_THROTTLE_SECONDS (from settings) to avoid
Steam's unofficial rate limit. All errors are caught + surfaced as ApiError
so the scheduler keeps tracking other apps if one fails.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

log = logging.getLogger("tracker.steam_api")

APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2"
APPLIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2"

# Steam news feed names that indicate a *real* app update.
UPDATE_FEEDS = {
    "steam_community_announcements",
    "product_update",
    "product_release",
}

_last_request_ts: Dict[str, float] = {"last": 0.0}


class ApiError(RuntimeError):
    """Raised when Steam returns an error or is unreachable."""


def _throttle() -> None:
    now = time.time()
    wait = settings.STEAM_THROTTLE_SECONDS - (now - _last_request_ts["last"])
    if wait > 0:
        time.sleep(wait)
    _last_request_ts["last"] = time.time()


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    headers = {
        "User-Agent": "SteamTrackerDjango/0.1 (+https://store.steampowered.com)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            _throttle()
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code == 429:
                log.warning("Steam returned 429 (rate-limited); sleeping 30s")
                time.sleep(30)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            log.warning("Steam request failed (attempt %d): %s",
                        attempt + 1, exc)
            time.sleep(5 * (attempt + 1))
    raise ApiError(f"Steam request failed after 3 attempts: {last_exc}")


# --- Typed result containers ----------------------------------------------

@dataclass
class AppSnapshot:
    appid: int
    name: str = ""
    type: str = ""
    is_free: bool = False
    currency: str = ""
    price_initial: int = 0
    price_final: int = 0
    discount_percent: int = 0
    release_date: str = ""
    last_update: int = 0
    developers: List[str] = field(default_factory=list)
    publishers: List[str] = field(default_factory=list)
    short_description: str = ""


@dataclass
class NewsItem:
    appid: int
    gid: str
    title: str = ""
    url: str = ""
    author: str = ""
    feed: str = ""
    is_update: bool = False
    contents: str = ""
    date: int = 0


# --- Public API ------------------------------------------------------------

def fetch_app_snapshot(appid: int) -> AppSnapshot:
    """Fetch appdetails (price, name, release info, last_update)."""
    payload = _get(APPDETAILS_URL, {
        "appids": appid,
        "cc": settings.STEAM_CC,
        "l": settings.STEAM_LANG,
    })
    data = payload.get(str(appid), {})
    if not data or not data.get("success"):
        raise ApiError(f"Steam appdetails: app {appid} not found or not success")
    info = data["data"]
    po = info.get("price_overview") or {}
    rel = info.get("release_date") or {}
    snap = AppSnapshot(
        appid=appid,
        name=info.get("name", ""),
        type=info.get("type", ""),
        is_free=bool(info.get("is_free", False)),
        currency=po.get("currency", ""),
        price_initial=int(po.get("initial", 0) or 0),
        price_final=int(po.get("final", 0) or 0),
        discount_percent=int(po.get("discount_percent", 0) or 0),
        release_date=rel.get("date", "") or "",
        last_update=int(info.get("last_update", 0) or 0),
        developers=list(info.get("developers", []) or []),
        publishers=list(info.get("publishers", []) or []),
        short_description=info.get("short_description", "") or "",
    )
    log.debug("snapshot %d: %s — final=%d %s (discount %d%%)",
              appid, snap.name, snap.price_final,
              snap.currency, snap.discount_percent)
    return snap


def fetch_app_news(appid: int, count: int = 20) -> List[NewsItem]:
    """Fetch recent news/announcements for an app."""
    payload = _get(NEWS_URL, {
        "appid": appid,
        "count": count,
        "maxlength": 0,
        "feeds": "steam_community_announcements",
    })
    news_payload = (payload.get("appnews") or {}).get("newsitems") or []
    out: List[NewsItem] = []
    for raw in news_payload:
        feed = str(raw.get("feed_name") or raw.get("feedlabel") or "")
        is_update = any(uf in feed.lower() for uf in UPDATE_FEEDS) or \
                    "patch" in (raw.get("title", "") or "").lower() or \
                    "hotfix" in (raw.get("title", "") or "").lower() or \
                    "update" in (raw.get("title", "") or "").lower()
        out.append(NewsItem(
            appid=appid,
            gid=str(raw.get("gid") or ""),
            title=str(raw.get("title") or ""),
            url=str(raw.get("url") or ""),
            author=str(raw.get("author") or ""),
            feed=feed,
            is_update=is_update,
            contents=str(raw.get("contents") or ""),
            date=int(raw.get("date", 0) or 0),
        ))
    log.debug("news %d: fetched %d items (%d update-flagged)",
              appid, len(out), sum(1 for n in out if n.is_update))
    return out


def resolve_app_name(appid: int) -> Optional[str]:
    """Look up a name from Steam's public app-list (for the Add-App form)."""
    payload = _get(APPLIST_URL, {})
    for entry in (payload.get("applist") or {}).get("apps", []) or []:
        if int(entry.get("appid", -1)) == appid:
            return entry.get("name")
    return None
