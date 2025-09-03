from os import getenv

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_mail import Message
from werkzeug.wrappers import Response

from app import app, limiter
from app.forms import ContactForm
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
