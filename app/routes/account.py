from flask import Blueprint, flash, redirect, url_for, request, render_template
from flask_login import login_required, current_user

from app import db
from app.forms import BioForm

account_bp: Blueprint = Blueprint("account", __name__)


@account_bp.route("/account/update_preferences", methods=["POST"])
@login_required
def update_preferences():
    current_user.newsletter = "newsletter" in request.form
    current_user.email_notifications = "email_notifications" in request.form
    db.session.commit()
    flash("Preferences updated successfully.", "success")
    return redirect(url_for("blog.user_posts", username=current_user.username))


@account_bp.route("/account/update_bio", methods=["POST"])
@login_required
def update_bio():
    form = BioForm()
    if form.validate_on_submit():
        # Update bio using the model method (no social links)
        current_user.update_bio(
            bio_text=form.bio_text.data,
            location=form.location.data,
            website=form.website.data,
            social_links={}
        )
        
        db.session.commit()
        flash("Bio updated successfully.", "success")
    else:
        # Flash form errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "error")
    
    return redirect(url_for("blog.user_posts", username=current_user.username))
