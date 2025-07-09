from dataclasses import dataclass, asdict
from functools import wraps

from bs4 import BeautifulSoup
from bleach import clean, sanitizer
from feedparser import FeedParserDict, parse
from flask import abort
from markupsafe import Markup
from markdown import markdown
from requests import get
from requests.exceptions import RequestException

ALLOWED_TAGS = [
    # inline
    'a','abbr','acronym','b','blockquote','code','em','i','strong',
    # lists
    'ul','ol','li',
    # headings & sections
    'h1','h2','h3','h4','h5','h6','p','hr',
    # code & pre
    'pre',
    # images
    'img',
    # tables
    'table','thead','tbody','tr','th','td',
]
ALLOWED_ATTRS = {
    'a':      ['href','title'],
    'img':    ['src','alt','title','width','height'],
    'blockquote': ['class','data-lang'],
    'pre':    ['class','data-lang'],
    'code':   ['class'],
    # if you want to allow CSS classes on lists/tables:
    'ul':     ['class'],  
    'ol':     ['class'],
    'li':     ['class'],
    'table':  ['class'],
    'thead':  ['class'],
    'tbody':  ['class'],
    'tr':     ['class'],
    'th':     ['class','colspan','rowspan'],
    'td':     ['class','colspan','rowspan'],
}

@dataclass
class Gatherings:
    title: str
    time: str
    description: str



def md(text: str) -> Markup:
    """Render Markdown to HTML, sanitize, and mark safe for Jinja."""
    # 1. Convert Markdown to HTML
    html = markdown(
        text,
        extensions=['fenced_code','tables','smarty']
    )
    # 2. Clean it, stripping any tag not in ALLOWED_TAGS
    cleaned = clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True
    )
    # 3. Wrap it so Jinja knows it's already safe HTML
    return Markup(cleaned)


def get_rss_highlights():
    feeds = [
        "https://www.boston.com/tag/national-news/feed",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://www.eff.org/rss/updates.xml",
    ]
    headlines = []
    for url in feeds:
        feed: FeedParserDict = parse(url)
        if feed.entries:
            headlines.append({
                "source": feed.feed.title,
                "content": [{
                    "title": entry.title,
                    "link": entry.link
                } for entry in feed.entries[:3]]
            })
    return headlines


def roles_required(*allowed):

    def decorator(f):

        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return abort(403)
            role = getattr(current_user, "role", None)
            if role not in allowed:
                return abort(403)
            return f(*args, **kwargs)

        return wrapped

    return decorator


def scrape_events():
    url = "https://masspeaceaction.org/events/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    events = []
    try:
        response = get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        event_articles = soup.find_all("article", class_="tribe-events-calendar-list__event")
        for article in event_articles:
            title_elem = article.find("a", class_="tribe-events-calendar-list__event-title-link")
            time_elem = article.find("time", class_="tribe-events-calendar-list__event-datetime")
            venue_elem = article.find("address", class_="tribe-events-calendar-list__event-venue")
            title = title_elem.get_text(strip=True) if title_elem else "No title"
            link = title_elem["href"] if title_elem and "href" in title_elem.attrs else "#"
            time_str = time_elem.get_text(strip=True) if time_elem else "Time not available"
            location = venue_elem.get_text(strip=True, separator="; ") if venue_elem else "Location not available"
            events.append({
                "title": title,
                "link": link,
                "time": time_str,
                "location": location,
            })
    except RequestException as e:
        print(f"Error scraping events: {e}")
        return []
    return events


def get_gatherings() -> list[dict[str, str]]:
    return [
        asdict(Gatherings(
            title="Introduction",
            time="Thurs June 26 @ 5:00 pmEDT",
            description="First activism night meeting"
        ))
    ]
