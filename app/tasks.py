from os import getenv
from functools import partial
from typing import Optional

from datetime import datetime, timezone, timedelta
from flask import render_template
from flask_mail import Message

from app import app
from app.models import Post, Comment, PostLike, User


timestamp = partial(datetime.now, timezone.utc)
MAIL_NEWSLETTER = getenv("MAIL_NEWSLETTER")


def get_weekly_stats() -> Optional[Post] | int:
    cutoff = timestamp() - timedelta(days=7)
    best, best_score = None, -1
    post: Post
    for post in Post.query:
        c_count = Comment.query.filter(
            Comment.post_id == post.id, Comment.timestamp >= cutoff
        ).count()
        l_count = PostLike.query.filter(
            PostLike.post_id == post.id, Comment.timestamp >= cutoff
        ).count()
        score = c_count + l_count
        if score > best_score:
            best, best_score = post, score
    return best, best_score


def send_weekly_top_post_email():
    post, score = get_weekly_stats()
    if not post:
        return
    cutoff = timestamp() - timedelta(days=7)
    comments = Comment.query.filter(
        Comment.post_id == post.id, Comment.timestamp >= cutoff
    ).all()
    likes = PostLike.query.filter(
        PostLike.post_id == post.id, PostLike.timestamp >= cutoff
    ).all()
    text_body = render_template(
        "emails/weekly_top_post.txt",
        post=post,
        comments=comments,
        likes=likes,
        score=score,
    )
    html_body = render_template(
        "emails/weekly_top_post.html",
        post=post,
        comments=comments,
        likes=likes,
        score=score,
    )
    app.config["MAIL_DEFAULT_SENDER"] = MAIL_NEWSLETTER
    subscribers = User.query.filter_by(newsletter=True).all()
    msg = Message(
        subject=f"Weekly Top Post: {post.title}",
        recipients=[user.email for user in subscribers],
        body=text_body,
        html=html_body,
    )
    app.mail.send(msg)
