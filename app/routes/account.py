from flask import Blueprint, flash, redirect, url_for, request
from flask_login import login_required, current_user

from app import db

account_bp: Blueprint = Blueprint("account", __name__)


@account_bp.route('/account/update_preferences', methods=['POST'])
@login_required
def update_preferences():
    current_user.newsletter = 'newsletter' in request.form
    current_user.email_notifications = 'email_notifications' in request.form
    db.session.commit()
    flash("Preferences updated successfully.", "success")
    return redirect(url_for('blog.user_posts', username=current_user.username))
