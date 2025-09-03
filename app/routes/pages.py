from os import getenv
import secrets

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_mail import Message
from werkzeug.wrappers import Response

from app import app, limiter, db
from app.forms import ContactForm, NewsletterForm
from app.models import NewsletterSubscription, User
from app.email_utils import send_email_with_config

pages_bp = Blueprint("pages", __name__)
MAIL_CONTACT = getenv("SMTP_USER")


@pages_bp.route("/about")
def about():
    return render_template("about.html")


@pages_bp.route("/terms")
def terms():
    return render_template("terms.html")


@pages_bp.route("/privacy")
def privacy():
    return render_template("privacy.html")


@limiter.limit("2 per day")
def send_mail(form: ContactForm) -> Response:
    text_body = render_template(
        "emails/contact.txt",
        name=form.name.data,
        email=form.email.data,
        subject=form.subject.data,
        message=form.message.data,
    )
    html_body = render_template(
        "emails/contact.html",
        name=form.name.data,
        email=form.email.data,
        subject=form.subject.data,
        message=form.message.data,
    )
    
    success = send_email_with_config(
        email_type="contact",
        subject=f"[Contact] {form.subject.data}",
        recipients=[MAIL_CONTACT],
        text_body=text_body,
        html_body=html_body,
        reply_to=form.email.data
    )
    
    if success:
        flash("Thanks! Your message has been sent.", "success")
    else:
        flash("Sorry, there was an error sending your message. Please try again.", "error")
    
    return redirect(url_for("blog.index"))


@pages_bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        return send_mail(form)
    return render_template("contact.html", form=form)


@pages_bp.route("/contributing")
def contributing():
    return render_template("contributing.html")


@limiter.limit("5 per hour")
@pages_bp.route("/newsletter/subscribe", methods=["POST"])
def subscribe_newsletter():
    """Handle newsletter subscription for guests"""
    form = NewsletterForm()
    
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        
        # Check if email is already subscribed (either as user or guest)
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.newsletter:
            return jsonify({
                'success': False,
                'message': 'This email is already subscribed to our newsletter.'
            }), 400
        
        existing_guest = NewsletterSubscription.query.filter_by(email=email).first()
        if existing_guest and existing_guest.is_active:
            return jsonify({
                'success': False,
                'message': 'This email is already subscribed to our newsletter.'
            }), 400
        
        # If guest subscription exists but is inactive, reactivate it
        if existing_guest and not existing_guest.is_active:
            existing_guest.is_active = True
            existing_guest.unsubscribe_token = secrets.token_urlsafe(32)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Welcome back! You\'ve been resubscribed to our newsletter.'
            })
        
        # Create new guest subscription
        unsubscribe_token = secrets.token_urlsafe(32)
        new_subscription = NewsletterSubscription(
            email=email,
            unsubscribe_token=unsubscribe_token,
            is_active=True
        )
        
        try:
            db.session.add(new_subscription)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Thank you for subscribing to our newsletter!'
            })
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error creating newsletter subscription: {e}")
            return jsonify({
                'success': False,
                'message': 'Sorry, there was an error subscribing you. Please try again.'
            }), 500
    
    # Form validation failed
    errors = {}
    for field, field_errors in form.errors.items():
        errors[field] = field_errors[0] if field_errors else 'Invalid input'
    
    return jsonify({
        'success': False,
        'message': 'Please check your email address and try again.',
        'errors': errors
    }), 400


@pages_bp.route("/newsletter/unsubscribe/<token>")
def unsubscribe_newsletter(token):
    """Handle newsletter unsubscription for guests"""
    subscription = NewsletterSubscription.query.filter_by(unsubscribe_token=token).first()
    
    if not subscription:
        flash("Invalid unsubscribe link.", "error")
        return redirect(url_for("blog.index"))
    
    if not subscription.is_active:
        flash("You are already unsubscribed from our newsletter.", "info")
        return redirect(url_for("blog.index"))
    
    subscription.is_active = False
    db.session.commit()
    
    flash("You have been unsubscribed from our newsletter.", "success")
    return redirect(url_for("blog.index"))
