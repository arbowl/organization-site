from flask import Blueprint, flash, redirect, url_for, request, render_template
from flask_login import login_required, current_user
from itsdangerous import URLSafeTimedSerializer
from os import getenv

from app import db
from app.forms import BioForm, ChangePasswordForm
from app.models import User, Tag

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
    # Get all available tags for the form choices
    all_tags = Tag.query.order_by(Tag.name).all()
    form = BioForm()
    form.favorite_tags.choices = [(tag.id, tag.name) for tag in all_tags]
    
    if form.validate_on_submit():
        # Update bio using the model method (no social links)
        current_user.update_bio(
            bio_text=form.bio_text.data,
            location=form.location.data,
            website=form.website.data,
            social_links={},
            favorite_tags=form.favorite_tags.data
        )
        
        db.session.commit()
        flash("Bio updated successfully.", "success")
    else:
        # Flash form errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{field}: {error}", "error")
    
    return redirect(url_for("blog.user_posts", username=current_user.username))


def generate_unsubscribe_token(user_id: int, email_type: str) -> str:
    """Generate a secure token for unsubscribe links."""
    serializer = URLSafeTimedSerializer(getenv('SECRET_KEY', 'fallback-secret-key'))
    return serializer.dumps({'user_id': user_id, 'email_type': email_type})


def verify_unsubscribe_token(token: str) -> tuple[int, str] | None:
    """Verify and decode an unsubscribe token."""
    try:
        serializer = URLSafeTimedSerializer(getenv('SECRET_KEY', 'fallback-secret-key'))
        data = serializer.loads(token, max_age=86400)  # 24 hours
        return data['user_id'], data['email_type']
    except:
        return None


@account_bp.route("/unsubscribe/<token>")
def unsubscribe(token):
    """Handle unsubscribe requests from email links."""
    result = verify_unsubscribe_token(token)
    if not result:
        flash("Invalid or expired unsubscribe link.", "error")
        return redirect(url_for("blog.index"))
    
    user_id, email_type = result
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("blog.index"))
    
    if email_type == "newsletter":
        user.newsletter = False
        message = "You have been unsubscribed from the newsletter."
    elif email_type == "notifications":
        user.email_notifications = False
        message = "You have been unsubscribed from email notifications."
    else:
        flash("Invalid email type.", "error")
        return redirect(url_for("blog.index"))
    
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("blog.index"))


@account_bp.route("/unsubscribe/manage/<token>")
def manage_subscriptions(token):
    """Allow users to manage their email preferences via token."""
    result = verify_unsubscribe_token(token)
    if not result:
        flash("Invalid or expired link.", "error")
        return redirect(url_for("blog.index"))
    
    user_id, _ = result
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("blog.index"))
    
    return render_template("manage_subscriptions.html", user=user, token=token)


@account_bp.route("/unsubscribe/update/<token>", methods=["POST"])
def update_preferences_via_token(token):
    """Update email preferences via token (for non-logged-in users)."""
    result = verify_unsubscribe_token(token)
    if not result:
        flash("Invalid or expired link.", "error")
        return redirect(url_for("blog.index"))
    
    user_id, _ = result
    user = User.query.get(user_id)
    
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("blog.index"))
    
    user.newsletter = "newsletter" in request.form
    user.email_notifications = "email_notifications" in request.form
    db.session.commit()
    
    flash("Preferences updated successfully.", "success")
    return redirect(url_for("account.manage_subscriptions", token=token))


@account_bp.route("/account/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Allow users to change their password."""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Verify current password
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html", form=form)
        
        # Set new password
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        flash("Your password has been changed successfully.", "success")
        return redirect(url_for("blog.user_posts", username=current_user.username))
    
    return render_template("auth/change_password.html", form=form)
