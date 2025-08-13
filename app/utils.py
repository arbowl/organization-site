from colorsys import rgb_to_hls, hls_to_rgb
from hashlib import md5

from bs4 import BeautifulSoup
from bleach import clean
from feedparser import FeedParserDict, parse
from markupsafe import Markup
from markdown import markdown
from requests import get
from requests.exceptions import RequestException


SAFE_HUE_CENTERS = [
    18,   # peach/coral
    30,   # soft orange
    150,  # mint
    175,  # teal
    200,  # cyan
    222,  # sky/blue
    245,  # indigo
    272,  # violet
    315,  # pink
]
ALLOWED_TAGS = [
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "code",
    "em",
    "i",
    "strong",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "hr",
    "pre",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]
ALLOWED_ATTRS = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "blockquote": ["class", "data-lang"],
    "pre": ["class", "data-lang"],
    "code": ["class"],
    "ul": ["class"],
    "ol": ["class"],
    "li": ["class"],
    "table": ["class"],
    "thead": ["class"],
    "tbody": ["class"],
    "tr": ["class"],
    "th": ["class", "colspan", "rowspan"],
    "td": ["class", "colspan", "rowspan"],
}


def md(text: str) -> Markup:
    """Render Markdown to HTML, sanitize, and mark safe for Jinja."""
    html = markdown(text, extensions=["fenced_code", "tables", "smarty"])
    cleaned = clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    return Markup(cleaned)


def get_rss_highlights():
    """Pulls international and local news sources"""
    feeds = [
        "https://www.boston.com/tag/national-news/feed",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://www.eff.org/rss/updates.xml",
    ]
    headlines = []
    for url in feeds:
        feed: FeedParserDict = parse(url)
        if feed.entries:
            headlines.append(
                {
                    "source": feed.feed.title,
                    "content": [
                        {"title": entry.title, "link": entry.link}
                        for entry in feed.entries[:3]
                    ],
                }
            )
    return headlines


def scrape_events():
    """Pulls local MA protests from Mass Peace Action"""
    url = "https://masspeaceaction.org/events/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    events = []
    try:
        response = get(url, headers=headers, timeout=1)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        event_articles = soup.find_all(
            "article", class_="tribe-events-calendar-list__event"
        )
        for article in event_articles:
            title_elem = article.find(
                "a", class_="tribe-events-calendar-list__event-title-link"
            )
            time_elem = article.find(
                "time", class_="tribe-events-calendar-list__event-datetime"
            )
            venue_elem = article.find(
                "address", class_="tribe-events-calendar-list__event-venue"
            )
            title = title_elem.get_text(strip=True) if title_elem else "No title"
            link = (
                title_elem["href"] if title_elem and "href" in title_elem.attrs else "#"
            )
            time_str = (
                time_elem.get_text(strip=True) if time_elem else "Time not available"
            )
            location = (
                venue_elem.get_text(strip=True, separator="; ")
                if venue_elem
                else "Location not available"
            )
            events.append(
                {
                    "title": title,
                    "link": link,
                    "time": time_str,
                    "location": location,
                }
            )
    except RequestException as e:
        print(f"Error scraping events: {e}")
        return []
    return events


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def color_from_slug(
    slug: str,
    lightness_center=0.58,
    lightness_range=0.05,
    saturation_center=0.55,
    saturation_range=0.10,
    grayscale_ratio=0.05
):
    h = md5(slug.encode("utf-8")).digest()
    gray_gate = h[0] / 255.0
    if gray_gate < grayscale_ratio:
        L_jitter = ((h[1] / 255.0) - 0.5) * 0.06
        S_jitter = ((h[2] / 255.0) - 0.5) * 0.06
        L = clamp(0.88 + L_jitter, 0.84, 0.92)
        S = clamp(0.04 + S_jitter, 0.02, 0.08)
        H = 0.0
    else:
        band_count = len(SAFE_HUE_CENTERS)
        band_index = int((h[1] / 255.0) * band_count) % band_count
        H = SAFE_HUE_CENTERS[band_index] / 360.0
        S = clamp(
            saturation_center + ((h[2] / 255.0) - 0.5) * (2 * saturation_range),
            saturation_center - saturation_range,
            saturation_center + saturation_range
        )
        L = clamp(
            lightness_center + ((h[3] / 255.0) - 0.5) * (2 * lightness_range),
            lightness_center - lightness_range,
            lightness_center + lightness_range
        )
    r, g, b = hls_to_rgb(H, L, S)
    R, G, B = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
    return f"#{R:02x}{G:02x}{B:02x}"