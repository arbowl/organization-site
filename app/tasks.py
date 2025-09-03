from os import getenv
from functools import partial
from typing import Optional
import requests
from bs4 import BeautifulSoup
import re

from datetime import datetime, timezone, timedelta
from flask import render_template
from flask_mail import Message

from app import app
from app.models import Post, Comment, PostLike, User, Bill, NewsletterSubscription, db
from app.email_utils import send_email_with_config


timestamp = partial(datetime.now, timezone.utc)


def get_weekly_stats() -> Optional[Post] | int:
    cutoff = timestamp() - timedelta(days=7)
    best, best_score = None, -1
    post: Post
    for post in Post.query:
        c_count = Comment.query.filter(
            Comment.post_id == post.id, Comment.timestamp >= cutoff
        ).count()
        l_count = PostLike.query.filter(
            PostLike.post_id == post.id, PostLike.timestamp >= cutoff
        ).count()
        score = c_count + l_count
        if score > best_score:
            best, best_score = post, score
    return best, best_score


def send_weekly_top_post_email():
    with app.app_context():
        with app.test_request_context():
            post, score = get_weekly_stats()
            if not post:
                return
            cutoff = timestamp() - timedelta(days=7)
            comments = Comment.query.filter(
                Comment.post_id == post.id, Comment.timestamp >= cutoff
            ).all()
            likes = PostLike.query.filter(
                PostLike.post_id == post.id, PostLike.timestamp >= cutoff
            ).all()
            
            # Get both registered user subscribers and guest subscribers
            user_subscribers = User.query.filter_by(newsletter=True).all()
            guest_subscribers = NewsletterSubscription.query.filter_by(is_active=True).all()
            
            all_subscribers = []
            
            # Add registered users
            for user in user_subscribers:
                all_subscribers.append({
                    'email': user.email,
                    'user': user,
                    'is_guest': False
                })
            
            # Add guest subscribers
            for guest in guest_subscribers:
                all_subscribers.append({
                    'email': guest.email,
                    'user': None,
                    'is_guest': True,
                    'subscription': guest
                })
            
            if all_subscribers:
                # Send individual emails to each subscriber so we can include unsubscribe links
                for subscriber in all_subscribers:
                    text_body = render_template(
                        "emails/weekly_top_post.txt",
                        post=post,
                        comments=comments,
                        likes=likes,
                        score=score,
                        user=subscriber['user'],
                        is_guest=subscriber['is_guest'],
                        subscription=subscriber.get('subscription'),
                    )
                    html_body = render_template(
                        "emails/weekly_top_post.html",
                        post=post,
                        comments=comments,
                        likes=likes,
                        score=score,
                        user=subscriber['user'],
                        is_guest=subscriber['is_guest'],
                        subscription=subscriber.get('subscription'),
                    )
                    
                    success = send_email_with_config(
                        email_type="newsletter",
                        subject=f"Weekly Top Post: {post.title}",
                        recipients=[subscriber['email']],
                        text_body=text_body,
                        html_body=html_body
                    )
                    
                    if not success:
                        app.logger.error(f"Failed to send weekly newsletter email to {subscriber['email']}")


def scrape_ma_bills():
    """Scrape bills from the MA Legislature website and create/update bill records"""
    with app.app_context():
        try:
            # Scrape the recent bills page
            url = "https://malegislature.gov/Bills/RecentBills"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all bills tables (Recent Bills and Popular Bills)
            bills_tables = soup.find_all('table')
            if not bills_tables:
                app.logger.error("Could not find bills tables on MA Legislature page")
                return
            
            bills_processed = 0
            bills_created = 0
            
            # Process each table (Recent Bills and Popular Bills)
            for table_num, bills_table in enumerate(bills_tables, 1):
                app.logger.info(f"Processing table {table_num} ({'Recent Bills' if table_num == 1 else 'Popular Bills'})")
                
                # Process each row in the table
                for row in bills_table.find_all('tr')[1:]:  # Skip header row
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        # Extract bill information
                        bill_link = cells[1].find('a')
                        if not bill_link:
                            continue
                            
                        bill_number = bill_link.text.strip()
                        title = cells[2].text.strip()
                        
                        # Skip if no bill number or title
                        if not bill_number or not title:
                            continue
                        
                        # Determine chamber from bill number
                        if bill_number.startswith('H.'):
                            chamber = 'House'
                        elif bill_number.startswith('S.'):
                            chamber = 'Senate'
                        elif bill_number.startswith('HD.') or bill_number.startswith('SD.'):
                            chamber = 'Joint'
                        else:
                            chamber = 'Unknown'
                        
                        # Check if bill already exists
                        existing_bill = Bill.query.filter_by(bill_number=bill_number).first()
                        
                        if existing_bill:
                            # Update existing bill
                            existing_bill.title = title
                            existing_bill.chamber = chamber
                            existing_bill.updated_at = timestamp()
                            existing_bill.last_scraped = timestamp()
                            bills_processed += 1
                            
                            # Try to scrape content if it doesn't have any or is too short
                            if not existing_bill.content or len(existing_bill.content) < 200:
                                try:
                                    scrape_bill_content(existing_bill)
                                except Exception as e:
                                    app.logger.warning(f"Failed to scrape content for existing {bill_number}: {e}")
                        else:
                            # Create new bill
                            new_bill = Bill(
                                bill_number=bill_number,
                                title=title,
                                chamber=chamber,
                                status='Active'
                            )
                            db.session.add(new_bill)
                            bills_created += 1
                            bills_processed += 1
                            
                            # Try to scrape bill content
                            try:
                                scrape_bill_content(new_bill)
                            except Exception as e:
                                app.logger.warning(f"Failed to scrape content for {bill_number}: {e}")
            
            # Commit all changes
            db.session.commit()
            
            app.logger.info(f"Bill scraping completed: {bills_processed} processed, {bills_created} created")
            
        except Exception as e:
            app.logger.error(f"Error scraping MA bills: {e}")
            db.session.rollback()


def scrape_bill_content(bill: Bill):
    """Scrape the full text content of a specific bill"""
    try:
        # Extract bill number components for URL construction
        # Remove dots from bill number for URL (e.g., H.4459 -> H4459)
        bill_number_clean = bill.bill_number.replace('.', '')
        
        if bill.bill_number.startswith('H.'):
            url = f"https://malegislature.gov/Bills/194/{bill_number_clean}/House/Bill/Text"
        elif bill.bill_number.startswith('S.'):
            url = f"https://malegislature.gov/Bills/194/{bill_number_clean}/Senate/Bill/Text"
        elif bill.bill_number.startswith('HD.'):
            url = f"https://malegislature.gov/Bills/194/{bill_number_clean}/House/Bill/Text"
        elif bill.bill_number.startswith('SD.'):
            url = f"https://malegislature.gov/Bills/194/{bill_number_clean}/Senate/Bill/Text"
        else:
            return
        
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the bill text content - try multiple selectors
        bill_text = None
        
        # Try different selectors for bill content
        selectors = [
            'div.bill-text',
            'div#bill-text', 
            'div.content',
            'div.bill-content',
            'pre',
            'div[class*="bill"]',
            'div[class*="text"]'
        ]
        
        for selector in selectors:
            bill_text = soup.select_one(selector)
            if bill_text:
                break
        
        # If still no content found, try to find any div with substantial text
        if not bill_text:
            # Look for divs with lots of text content
            all_divs = soup.find_all('div')
            for div in all_divs:
                text_content = div.get_text(strip=True)
                if len(text_content) > 500:  # Substantial content
                    bill_text = div
                    break
        
        if bill_text:
            # Clean up the text content
            content = bill_text.get_text(separator='\n', strip=True)
            
            # Remove excessive whitespace and clean up
            content = re.sub(r'\n\s*\n', '\n\n', content)
            content = re.sub(r'[ \t]+', ' ', content)  # Normalize spaces
            content = content.strip()
            
            # Only update if we got meaningful content (more than just a title)
            if content and len(content) > 200:
                bill.content = content
                bill.last_scraped = timestamp()
                app.logger.info(f"Successfully scraped content for {bill.bill_number} ({len(content)} chars)")
            else:
                app.logger.warning(f"Content too short for {bill.bill_number}: {len(content) if content else 0} chars")
        else:
            app.logger.warning(f"No bill content found for {bill.bill_number}")
        
    except Exception as e:
        app.logger.warning(f"Failed to scrape content for bill {bill.bill_number}: {e}")


def get_bills_for_display(limit: int = 10):
    """Get recent bills for display in the Hot Bills dropdown"""
    return Bill.query.order_by(Bill.created_at.desc()).limit(limit).all()


def scrape_all_bill_content():
    """Scrape content for all bills that don't have content yet"""
    with app.app_context():
        try:
            bills_without_content = Bill.query.filter(
                (Bill.content.is_(None)) | (Bill.content == '') | (db.func.length(Bill.content) < 200)
            ).all()
            
            app.logger.info(f"Found {len(bills_without_content)} bills without content")
            
            success_count = 0
            for bill in bills_without_content:
                try:
                    scrape_bill_content(bill)
                    if bill.content and len(bill.content) > 200:
                        success_count += 1
                except Exception as e:
                    app.logger.warning(f"Failed to scrape content for {bill.bill_number}: {e}")
            
            db.session.commit()
            app.logger.info(f"Content scraping completed: {success_count}/{len(bills_without_content)} bills updated")
            
        except Exception as e:
            app.logger.error(f"Error in scrape_all_bill_content: {e}")
            db.session.rollback()
