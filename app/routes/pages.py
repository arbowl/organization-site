from os import getenv

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_mail import Message
from werkzeug.wrappers import Response

from app import app, limiter
from app.forms import ContactForm

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
    msg = Message(
        subject=f"[Contact] {form.subject.data}",
        recipients=[MAIL_CONTACT],
        reply_to=form.email.data,
    )
    msg.body = render_template(
        "emails/contact.txt",
        name=form.name.data,
        email=form.email.data,
        subject=form.subject.data,
        message=form.message.data,
    )
    msg.html = render_template(
        "emails/contact.html",
        name=form.name.data,
        email=form.email.data,
        subject=form.subject.data,
        message=form.message.data,
    )
    app.config["MAIL_DEFAULT_SENDER"] = MAIL_CONTACT
    app.mail.send(msg)
    flash("Thanks! Your message has been sent.", "success")
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
