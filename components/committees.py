""" Fetches committee data from the Massachusetts Legislature website.
"""

import re
from urllib.parse import urljoin
from typing import Iterable, Set

import requests  # type: ignore
from bs4 import BeautifulSoup

from components.models import Committee

LISTING_PATHS = {
    "Joint": "/Committees/Joint",
    "House": "/Committees/House",
    # "Senate": "/Committees/Senate",  # intentionally unused
}

# Matches both styles we see on the site:
#   /Committees/Detail/J33   and   /Committees/Detail/H33
# (Some internal links may also look like /Committees/Joint/J14; the
# detail pages resolve to /Committees/Detail/J14. We normalize to Detail/)
DETAIL_HREF_RE = re.compile(
    r"/Committees/(?:Detail|Joint|House)/([JH]\d+)", re.I
)


def _fetch(session: requests.Session, url: str) -> BeautifulSoup:
    resp = session.get(
        url, timeout=20, headers={"User-Agent": "legis-scraper/0.1"}
    )
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _extract_from_listing(
    soup: BeautifulSoup, base_url: str, chamber: str
) -> Iterable[Committee]:
    seen: Set[str] = set()
    for a in soup.find_all("a", href=True):
        m: re.Match = DETAIL_HREF_RE.search(a["href"])  # type: ignore
        if not m:
            continue
        cid = m.group(1).upper()
        if cid[0] == "S":
            continue
        if cid in seen:
            continue
        seen.add(cid)
        name = " ".join(a.get_text(strip=True).split())
        detail_url = urljoin(base_url, f"/Committees/Detail/{cid}")
        yield Committee(id=cid, name=name, chamber=chamber, url=detail_url)


def get_committees(
    base_url: str, include_chambers: Iterable[str]
) -> list[Committee]:
    """
    Return all committees for the specified chambers (Joint/House only).
    """
    committees: list[Committee] = []
    with requests.Session() as s:
        for chamber in include_chambers:
            path = LISTING_PATHS.get(chamber)
            if not path:
                continue
            soup = _fetch(s, urljoin(base_url, path))
            committees.extend(
                list(_extract_from_listing(soup, base_url, chamber))
            )
    # Stable sort: Joint then House, by name, then id.
    committees.sort(key=lambda c: (c.chamber, c.name, c.id))
    return committees
