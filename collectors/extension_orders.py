"""Collect extension orders from the Massachusetts Legislature website."""

from __future__ import annotations

import re
from datetime import datetime, date
from typing import Optional, List, TYPE_CHECKING
from urllib.parse import urljoin

import requests  # type: ignore
from bs4 import BeautifulSoup

from components.models import ExtensionOrder
if TYPE_CHECKING:
    from components.utils import Cache


def _soup(session: requests.Session, url: str) -> BeautifulSoup:
    """Get the soup of the page."""
    r = session.get(url, timeout=20, headers={
        "User-Agent": "legis-scraper/0.1"
    })
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _extract_extension_date(text: str) -> Optional[date]:
    """Extract extension date from extension order text."""
    # Common date patterns in extension orders
    date_patterns = [
        # "Wednesday, December 3, 2025"
        (
            r'\b([A-Za-z]+day,?\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4})\b',
            '%A, %B %d, %Y'
        ),
        (
            r'\b([A-Za-z]+day,?\s+[A-Za-z]+\s+\d{1,2}\s+\d{4})\b',
            '%A, %B %d %Y'
        ),
        # "December 3, 2025"
        (r'\b([A-Za-z]+\s+\d{1,2},?\s+\d{4})\b', '%B %d, %Y'),
        (r'\b([A-Za-z]+\s+\d{1,2}\s+\d{4})\b', '%B %d %Y'),
        # "12/3/2025" or "12/03/2025"
        (r'\b(\d{1,2}/\d{1,2}/\d{4})\b', '%m/%d/%Y'),
        # "2025-12-03"
        (r'\b(\d{4}-\d{1,2}-\d{1,2})\b', '%Y-%m-%d'),
    ]
    for pattern, fmt in date_patterns:
        matches = re.findall(pattern, text, re.I)
        for match in matches:
            try:
                return datetime.strptime(match, fmt).date()
            except ValueError:
                continue
    return None


def _extract_committee_from_text(text: str) -> Optional[str]:
    """Extract committee ID from extension order text."""
    # Look for committee patterns in the text
    committee_patterns = [
        r'committee on ([^,\n]+)',
        r'Joint Committee on ([^,\n]+)',
        r'Committee on ([^,\n]+)',
    ]
    for pattern in committee_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            committee_name = match.group(1).strip()
            # Map common committee names to IDs (this could be expanded)
            committee_mapping = {
                'Telecommunications, Utilities, and Energy': 'J33',
                'Environment and Natural Resources': 'J16',
                'Education': 'J37',
                'Housing': 'J39',
                'Transportation': 'J40',
                'Economic Development and Emerging Technologies': 'J41',
                'Public Health': 'J42',
                # Add more mappings as needed
            }
            return committee_mapping.get(committee_name)
    return None


def _extract_bill_id_from_order_url(order_url: str) -> Optional[str]:
    """Extract bill ID from extension order URL as fallback.
    URLs are typically in format: /Bills/2025/H1234/House/Order/Text
    We need to extract the bill ID (H1234) from this pattern.
    """
    # Pattern to match the bill ID in the order URL
    # /Bills/YYYY/H1234/House/Order/Text or /Bills/YYYY/S1234/Senate/Order/Text
    bill_pattern = r"/Bills/\d+/([HS]\d+)/(?:House|Senate)/Order/Text"
    match = re.search(bill_pattern, order_url)
    if match:
        return match.group(1)
    return None


def _extract_bill_numbers_from_text(text: str) -> List[str]:
    """Extract bill numbers from extension order text.
    Looks for patterns like:
    - "House document numbered 357" -> "H357"
    - "Senate document numbered 43" -> "S43"
    - "Joint document numbered 12" -> "J12"
    """
    bill_numbers = []
    # Pattern to match chamber + document number(s)
    patterns = [
        # Single document: "House document numbered 357"
        r"(House|Senate|Joint)\s+document\s+numbered\s+(\d+)",
        r"(House|Senate|Joint)\s+document\s+No\.?\s*(\d+)",
        r"(House|Senate|Joint)\s+document\s+#(\d+)",
        r"current\s+(House|Senate|Joint)\s+document\s+numbered\s+(\d+)",
        r"current\s+(House|Senate|Joint)\s+document\s+No\.?\s*(\d+)",
        # Multiple documents: "current House documents numbered 2065, 2080,..."
        r"current\s+(House|Senate|Joint)\s+documents\s+"
        r"numbered\s+([\d,\s\sand]+)",
    ]
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            chamber = match.group(1).lower()
            doc_numbers_str = match.group(2)
            # Map chamber to prefix
            if chamber == "house":
                prefix = "H"
            elif chamber == "senate":
                prefix = "S"
            elif chamber == "joint":
                prefix = "J"
            else:
                continue
            # Handle document numbers (comma-separated, possibly with "and")
            if "," in doc_numbers_str or " and " in doc_numbers_str:
                # Split by comma and "and", then clean up each number
                parts = re.split(r",\s*|\s+and\s+", doc_numbers_str)
                doc_numbers = [
                    num.strip() for num in parts if num.strip().isdigit()
                ]
            else:
                # Single document number
                doc_numbers = [doc_numbers_str.strip()]
            # Create bill IDs for each document number
            for doc_number in doc_numbers:
                if doc_number.isdigit():
                    bill_id = f"{prefix}{doc_number}"
                    bill_numbers.append(bill_id)
    return bill_numbers


def _parse_extension_order_page(
    session: requests.Session, _base_url: str, order_url: str
) -> List[ExtensionOrder]:
    """Parse a single extension order page to extract details for all bills
    mentioned.
    """
    try:
        soup = _soup(session, order_url)
        text = soup.get_text(" ", strip=True)
        # Extract extension date
        extension_date = _extract_extension_date(text)
        is_date_fallback = False
        if not extension_date:
            # If no specific date found, we'll use a fallback date of 0
            # This will be handled later when we have the hearing date
            extension_date = date(1900, 1, 1)  # Placeholder date
            is_date_fallback = True
        # Extract committee ID
        committee_id = _extract_committee_from_text(text)
        if not committee_id:
            # Default to unknown committee if we can't determine it
            committee_id = "UNKNOWN"
        # Determine order type from the page title or content
        order_type = "Extension Order"
        if "Committee Extension Order" in text:
            order_type = "Committee Extension Order"
        elif "Joint Committee" in text:
            order_type = "Joint Committee Extension Order"
        # Extract all bill numbers mentioned in the text
        bill_numbers = _extract_bill_numbers_from_text(text)
        if not bill_numbers:
            print(
                f"No bill numbers found in extension order text: {order_url}"
            )
            # Fallback: extract bill ID from the order URL itself
            bill_id_from_url = _extract_bill_id_from_order_url(order_url)
            if bill_id_from_url:
                print(
                    f"  Fallback: Using bill ID from URL: {bill_id_from_url}"
                )
                bill_numbers = [bill_id_from_url]
                # Mark this as a fallback case
                is_fallback = True
            else:
                print(f"  Could not extract bill ID from URL: {order_url}")
                return []
        else:
            is_fallback = False
        # Create ExtensionOrder objects for each bill mentioned
        extension_orders = []
        for bill_id in bill_numbers:
            extension_orders.append(ExtensionOrder(
                bill_id=bill_id,
                committee_id=committee_id,
                extension_date=extension_date,
                extension_order_url=order_url,
                order_type=order_type,
                discovered_at=datetime.now(),
                is_fallback=is_fallback,
                is_date_fallback=is_date_fallback
            ))
        return extension_orders
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error parsing extension order {order_url}: {e}")
        return []


def collect_all_extension_orders(
    base_url: str, cache: Optional[Cache] = None
) -> List[ExtensionOrder]:
    """Collect all extension orders from the Massachusetts Legislature website.
    """
    extension_orders = []
    with requests.Session() as s:
        # Process only Bills search pages
        search_types = ["Bills"]
        for search_type in search_types:
            print(f"Scraping {search_type} extension orders...")
            page = 1
            max_pages = 10  # Reduced safety limit
            previous_first_10_links = None
            duplicate_page_count = 0
            while page <= max_pages:
                # Construct URL with page parameter
                url = f"{base_url}/Bills/Search"
                params = {"searchTerms": "extension order", "page": page}
                print(f"Scraping {search_type} page {page}...")
                try:
                    r = s.get(url, params=params, timeout=20, headers={
                        "User-Agent": "legis-scraper/0.1"
                    })
                    r.raise_for_status()
                    soup = BeautifulSoup(r.text, "html.parser")
                    # Find all bill links on this page that might have
                    # extension orders
                    # We'll check each bill for extension orders
                    bill_links = soup.find_all(
                        "a", href=re.compile(r"/Bills/\d+/(H|S)\d+")
                    )
                    if not bill_links:
                        print(
                            f"No more bill links found on {search_type} page "
                            f"{page}"
                        )
                        break
                    print(
                        f"Found {len(bill_links)} total bill links on "
                        f"{search_type} page {page}"
                    )
                    # Get the first 10 bill links for duplicate detection
                    current_first_10_links = [
                        link.get("href", "") for link in bill_links[:10]
                    ]
                    # Check if we're getting duplicate content (first 10 links
                    # are the same)
                    if (
                        current_first_10_links == previous_first_10_links
                        and page > 1
                    ):
                        duplicate_page_count += 1
                        if duplicate_page_count >= 1:
                            print(
                                f"Detected duplicate content on {search_type} "
                                f"page {page} (first 10 entries match), "
                                f"stopping pagination"
                            )
                            break
                    else:
                        duplicate_page_count = 0
                    previous_first_10_links = current_first_10_links
                    for link in bill_links:
                        if hasattr(link, 'get'):
                            href = link.get("href", "")
                        else:
                            href = ""
                        if not href:
                            continue
                        bill_url = urljoin(base_url, href)
                        # Extract bill ID from URL to determine chamber
                        bill_match = re.search(r"/Bills/\d+/([HS]\d+)", href)
                        if not bill_match:
                            continue
                        bill_id = bill_match.group(1)
                        chamber = (
                            "House" if bill_id.startswith("H") else "Senate"
                        )
                        # Construct the Order/Text URL
                        order_url = f"{bill_url}/{chamber}/Order/Text"
                        # Check if this extension order exists by trying to
                        # fetch it
                        try:
                            test_response = s.head(order_url, timeout=10)
                            if test_response.status_code != 200:
                                continue
                        # pylint: disable=broad-exception-caught
                        except Exception:
                            continue
                        # Parse the extension order page
                        order_results = _parse_extension_order_page(
                            s, base_url, order_url
                        )
                        for extension_order in order_results:
                            extension_orders.append(extension_order)
                            if extension_order.is_fallback:
                                print(
                                    f"Found fallback extension order: "
                                    f"{extension_order.bill_id} -> "
                                    f"{extension_order.extension_date}"
                                )
                            else:
                                print(
                                    f"Found extension order: "
                                    f"{extension_order.bill_id} -> "
                                    f"{extension_order.extension_date}"
                                )
                            # Cache the extension immediately if cache is
                            # provided for non-fallback cases
                            if cache:
                                cache.set_extension(
                                    extension_order.bill_id,
                                    extension_order.extension_date.isoformat(),
                                    extension_order.extension_order_url
                                )
                                print(
                                    f"  Cached extension for "
                                    f"{extension_order.bill_id}"
                                )
                                # For fallback cases, also add the bill to
                                # cache with extensions field
                                if extension_order.is_fallback:
                                    cache.add_bill_with_extensions(
                                        extension_order.bill_id
                                    )
                    page += 1
                # pylint: disable=broad-exception-caught
                except Exception as e:
                    print(f"Error processing {search_type} page {page}: {e}")
                    break
    print(f"Collected {len(extension_orders)} extension orders total")
    return extension_orders


def get_extension_orders_for_bill(
    extension_orders: List[ExtensionOrder], bill_id: str
) -> List[ExtensionOrder]:
    """Get all extension orders for a specific bill."""
    return [eo for eo in extension_orders if eo.bill_id == bill_id]


def get_latest_extension_date(
    extension_orders: List[ExtensionOrder], bill_id: str
) -> Optional[date]:
    """Get the latest extension date for a specific bill."""
    bill_extensions = get_extension_orders_for_bill(extension_orders, bill_id)
    if not bill_extensions:
        return None
    return max(eo.extension_date for eo in bill_extensions)
