from flask import Blueprint, redirect, url_for, abort, flash, request
from flask_login import current_user, login_required

from app import db
from app.models import PostSubscription, UserSubscription, User, Post

social_bp = Blueprint("social", __name__)


@social_bp.route("/subscribe/user/<username>", methods=["POST"])
@login_required
def subscribe_user(username):
    target: User = User.query.filter_by(username=username).first_or_404()
    if target.id == current_user.id:
        abort(400)
    sub = UserSubscription(subscriber_id=current_user.id, user_id=target.id)
    db.session.add(sub)
    try:
        db.session.commit()
        flash(f"Subscribed to {username}!", "success")
    except:  # pylint: disable = bare-except
        db.session.rollback()
        flash(f"You're already subscribed to {username}.", "info")
    return redirect(request.referrer or url_for("blog.user_posts", username=username))


@social_bp.route("/unsubscribe/user/<username>", methods=["POST"])
@login_required
def unsubscribe_user(username):
    target: User = User.query.filter_by(username=username).first_or_404()
    sub = UserSubscription.query.filter_by(
        subscriber_id=current_user.id, user_id=target.id
    ).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
        flash(f"Unsubscribed from {username}.", "warning")
    return redirect(request.referrer or url_for("blog.user_posts", username=username))


@social_bp.route("/subscribe/post/<int:post_id>", methods=["POST"])
@login_required
def subscribe_post(post_id):
    post: Post = Post.query.get_or_404(post_id)
    if post.author.id == current_user.id:
        abort(400)
    sub = PostSubscription(subscriber_id=current_user.id, post_id=post.id)
    db.session.add(sub)
    try:
        db.session.commit()
        flash("Subscribed to comments on this post!", "success")
    except:  # pylint: disable = bare-except
        db.session.rollback()
        flash("You're already subscribed to this post.", "info")
    return redirect(request.referrer or url_for("blog.view_post", slug=post.slug))


@social_bp.route("/unsubscribe/post/<int:post_id>", methods=["POST"])
@login_required
def unsubscribe_post(post_id):
    post: Post = Post.query.get_or_404(post_id)
    sub = PostSubscription.query.filter_by(
        subscriber_id=current_user.id, post_id=post.id
    ).first()
    if sub:
        db.session.delete(sub)
        db.session.commit()
        flash(f"Unsubscribed from comments on this post.", "warning")
    return redirect(request.referrer or url_for("blog.view_post", slug=post.slug))
