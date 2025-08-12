"""Auth"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, limiter
from app.models import User
from app.forms import LoginForm, RegistrationForm

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
