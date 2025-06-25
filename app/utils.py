from functools import wraps

from bs4 import BeautifulSoup
from bleach import clean, sanitizer
from feedparser import FeedParserDict, parse
from flask import abort
from markdown import markdown
from requests import get
from requests.exceptions import RequestException

ALLOWED = list(sanitizer.ALLOWED_TAGS) + ["p", "pre", "code", "h1", "h2", "h3", "table", "thead", "tbody", "tr", "td", "img"]


def md(text):
    return clean(markdown(text, extensions=["fenced_code", "tables"]), tags=ALLOWED, strip=True)


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