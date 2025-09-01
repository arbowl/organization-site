"""Custom Jinja2 template filters for the application."""

from datetime import datetime


def format_date(date_obj):
    """Format a datetime object to 'Month Day, Year' format.
    
    Args:
        date_obj: A datetime object or string representation
        
    Returns:
        Formatted date string like 'July 10, 2025'
    """
    if isinstance(date_obj, datetime):
        return date_obj.strftime("%B %d, %Y")
    elif isinstance(date_obj, str):
        try:
            # Try to parse string dates
            parsed_date = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            return parsed_date.strftime("%B %d, %Y")
        except ValueError:
            return str(date_obj)
    return str(date_obj)


def format_date_time(date_obj):
    """Format a datetime object to 'Month Day, Year at Hour:Minute' format.
    
    Args:
        date_obj: A datetime object or string representation
        
    Returns:
        Formatted date string like 'July 10, 2025 at 2:30 PM'
    """
    if isinstance(date_obj, datetime):
        return date_obj.strftime("%B %d, %Y at %I:%M %p")
    elif isinstance(date_obj, str):
        try:
            # Try to parse string dates
            parsed_date = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            return parsed_date.strftime("%B %d, %Y at %I:%M %p")
        except ValueError:
            return str(date_obj)
    return str(date_obj)


def format_date_short(date_obj):
    """Format a datetime object to 'Month Day' format.
    
    Args:
        date_obj: A datetime object or string representation
        
    Returns:
        Formatted date string like 'July 10'
    """
    if isinstance(date_obj, datetime):
        return date_obj.strftime("%b %d")
    elif isinstance(date_obj, str):
        try:
            # Try to parse string dates
            parsed_date = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            return parsed_date.strftime("%b %d")
        except ValueError:
            return str(date_obj)
    return str(date_obj) 