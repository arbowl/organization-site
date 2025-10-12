"""Auth"""

import secrets
from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, limiter
from app.models import User
from app.forms import LoginForm, RegistrationForm, ForgotPasswordForm, ResetPasswordForm
from app.email_utils import send_email_with_config

auth_bp: Blueprint = Blueprint("auth", __name__)


@auth_bp.route("login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user: User = User.query.filter_by(username=form.username.data).first()
        if user and user.is_banned():
            flash(
                "Your account has been banned for violating site conduct rules.",
                "warning",
            )
            return redirect(request.referrer or url_for("blog.index"))
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("blog.index"))
        flash("Invalid username or password.", "danger")
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("blog.index"))


@limiter.limit("2 per day")
def submit_registration(form: RegistrationForm):
    new_user = User(
        username=form.username.data,
        email=form.email.data,
        password_hash=generate_password_hash(form.password.data),
        newsletter=form.newsletter.data,
    )
    db.session.add(new_user)
    db.session.commit()
    flash("Registration successful--please login.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        return submit_registration(form)
    return render_template("auth/register.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("3 per hour")
def forgot_password():
    """Handle forgot password requests"""
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()

        # Always show success message to prevent email enumeration
        flash(
            "If an account exists with that email, you will receive a "
            "password reset link shortly.",
            "info"
        )

        if user:
            # Generate secure reset token
            token = secrets.token_urlsafe(32)
            user.reset_token = token
            expiry = datetime.now(timezone.utc) + timedelta(hours=1)
            user.reset_token_expiry = expiry
            db.session.commit()

            # Send reset email
            reset_url = url_for(
                "auth.reset_password", token=token, _external=True
            )

            try:
                send_email_with_config(
                    email_type="notification",
                    subject="Password Reset Request",
                    recipients=[user.email],
                    text_body=render_template(
                        "emails/password_reset.txt",
                        user=user,
                        reset_url=reset_url
                    ),
                    html_body=render_template(
                        "emails/password_reset.html",
                        user=user,
                        reset_url=reset_url
                    )
                )
            except Exception as e:
                # Log error but don't reveal to user
                print(f"Failed to send password reset email: {e}")

        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Handle password reset with token"""
    if current_user.is_authenticated:
        return redirect(url_for("blog.index"))

    token = request.args.get("token")
    if not token:
        flash("Invalid or missing reset token.", "danger")
        return redirect(url_for("auth.login"))

    # Find user with valid token
    user = User.query.filter_by(reset_token=token).first()

    if not user or not user.reset_token_expiry:
        flash("Invalid or expired reset token.", "danger")
        return redirect(url_for("auth.login"))

    # Check if token is expired
    if datetime.now(timezone.utc) > user.reset_token_expiry:
        flash(
            "This reset link has expired. Please request a new one.",
            "danger"
        )
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        # Update password and clear reset token
        user.password_hash = generate_password_hash(form.password.data)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()

        flash(
            "Your password has been reset successfully. You can now log in.",
            "success"
        )
        return redirect(url_for("auth.login"))

    return render_template(
        "auth/reset_password.html", form=form, token=token
    )
