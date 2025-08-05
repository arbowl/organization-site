"""Models"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import partial

from flask import url_for
from flask_login import UserMixin
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy.orm import foreign
from sqlalchemy.sql import and_
from werkzeug.security import generate_password_hash, check_password_hash

from app import db

timestamp = partial(datetime.now, timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    posts = db.relationship("Post", backref="author", lazy="dynamic")

    @property
    def role_icon(self):
        match self.role:
            case "admin":
                return "⭐"
            case "moderator":
                return "🛡️"
            case "contributor":
                return "📝"
            case "banned":
                return "🚫"
            case _:
                return "👤"

    def subscribed_to_user(self, user: User):
        return UserSubscription.query.filter_by(
            subscriber_id=self.id, user_id=user.id
        ).first() is not None

    def subscribed_to_post(self, post: Post):
        return PostSubscription.query.filter_by(
            subscriber_id=self.id, post_id=post.id
        ).first() is not None

    def is_admin(self):
        return self.role == "admin"

    def is_moderator(self):
        return self.role == "moderator"

    def is_authority(self):
        return self.role in ["admin", "moderator"]

    def is_contributor(self):
        return self.role in ["contributor", "admin", "moderator"]

    def is_banned(self):
        return self.role == "banned"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(140), nullable=False)
    slug = db.Column(db.String(140), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, index=True, default=timestamp())
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_at = db.Column(db.DateTime, index=True, nullable=True)
    comments = db.relationship(
        "Comment",
        backref="post",
        lazy="dynamic",
        cascade="all, delete-orphan"
    )

    @property
    def display_date(self):
        date = self.timestamp.strftime('%Y-%m-%d')
        if self.updated_at:
            date += f" ⸱ <i>(edited {self.updated_at.strftime('%Y-%m-%d')})</i>"
        return date


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp(), index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    guest_name = db.Column(db.String(80), nullable=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    is_removed = db.Column(db.Boolean, default=False, nullable=False)
    removed_by = db.Column(db.String(20), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    author = db.relationship("User", backref="comments", foreign_keys=[author_id])
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]), lazy="dynamic")

    @hybrid_method
    def descendant_count(self):
        total = self.replies.count()
        for reply in self.replies:
            total += reply.descendant_count()
        return total


class PostLike(db.Model):
    __tablename__ = "post_likes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp())
    user = db.relationship("User", backref="post_likes")
    post = db.relationship("Post", backref=db.backref("likes", lazy="dynamic", cascade="all, delete-orphan"))


class CommentLike(db.Model):
    __tablename__ = "comment_likes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp())
    user = db.relationship("User", backref="comment_likes")
    comment = db.relationship("Comment", backref=db.backref("likes", lazy="dynamic", cascade="all, delete-orphan"))


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    guest_name = db.Column(db.String(80), nullable=True)
    verb = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp(), index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    recipient = db.relationship(
        User,
        foreign_keys=[recipient_id],
        backref="notifications"
    )
    actor = db.relationship(
        User,
        foreign_keys=[actor_id],
    )
    post = db.relationship(
        Post,
        primaryjoin=and_(target_type == "post", foreign(target_id) == Post.id),
        viewonly=True,
    )
    comment = db.relationship(
        Comment,
        primaryjoin=and_(target_type == "comment", foreign(target_id) == Comment.id),
        viewonly=True
    )

    @property
    def snippet(self):
        text = ""
        if self.target_type == "post" and self.post:
            text = getattr(self.post, "content", "") or ""
        if self.target_type == "comment" and self.comment:
            text = getattr(self.comment, "content", "") or ""
        return (text[:100] + "...") if len(text) > 100 else text


class Report(db.Model):
    __tablename__ = "reports"
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    reason = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=timestamp(), index=True)
    status = db.Column(db.String(20), nullable=False, default="new")
    handled_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    handled_at = db.Column(db.DateTime, nullable=True)
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    handler = db.relationship("User", foreign_keys=[handled_by])
    post = db.relationship("Post", backref="reports")
    comment = db.relationship("Comment", backref="reports")

    @property
    def target_url(self):
        if self.post_id:
            return url_for("blog.view_post", slug=self.post.slug)
        elif self.comment_id:
            return url_for("blog.view_post", slug=self.comment.post.slug) + f"#c{self.comment.id}"


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=timestamp())
    __table_args__ = (
        db.UniqueConstraint("subscriber_id", "user_id", name="uq_user_sub"),
    )


class PostSubscription(db.Model):
    __tablename__ = "post_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=timestamp())
    __table_args__ = (
        db.UniqueConstraint("subscriber_id", "post_id", name="uq_post_sub"),
    )


class Visit(db.Model):
    __tablename__ = 'visits'

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    path = db.Column(db.String(200), nullable=False)
    referrer = db.Column(db.String(500), nullable=True)
    utm_source = db.Column(db.String(100), nullable=True)
    utm_medium = db.Column(db.String(100), nullable=True)
    utm_campaign = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
