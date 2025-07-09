"""Models"""

from datetime import datetime, timezone
from functools import partial
from flask_login import UserMixin
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

    def is_admin(self):
        return self.role == "admin"

    def is_moderator(self):
        return self.role == "moderator"

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
    timestamp = db.Column(db.DateTime, index=True, default=timestamp)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=True)
    author = db.relationship("User", backref="comments")
    post = db.relationship("Post", backref=db.backref("comments", lazy="dynamic"))
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]), lazy="dynamic")


class PostLike(db.Model):
    __tablename__ = "post_likes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp)
    user = db.relationship("User", backref="post_likes")
    post = db.relationship("Post", backref=db.backref("likes", lazy="dynamic"))


class CommentLike(db.Model):
    __tablename__ = "comment_likes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey("comments.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=timestamp)
    user = db.relationship("User", backref="comment_likes")
    comment = db.relationship("Comment", backref=db.backref("likes", lazy="dynamic"))
