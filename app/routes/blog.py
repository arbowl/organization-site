"""Blog

This handles any routes related to the blog post portion of the site.
"""

from os import getenv

from datetime import datetime, timezone
from functools import partial
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from flask_mail import Message
from slugify import slugify
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError

from app import app, db, limiter
from app.models import (
    Post,
    User,
    Comment,
    PostLike,
    CommentLike,
    Notification,
    Report,
    UserSubscription,
    PostSubscription,
)
from app.forms import PostForm, CommentForm, SearchForm, CommentEditForm
from app.utils import get_rss_highlights, scrape_events

blog_bp: Blueprint = Blueprint("blog", __name__)
timestamp = partial(datetime.now, timezone.utc)
MAIL_NOTIFICATION = getenv("MAIL_NOTIFICATIONS")


@blog_bp.route("/")
def index() -> str:
    """The landing page of the site"""
    comment_count_subq = (
        db.session.query(Comment.post_id, func.count(Comment.id).label("comment_count"))
        .group_by(Comment.post_id)
        .subquery()
    )
    like_count_subq = (
        db.session.query(PostLike.post_id, func.count(PostLike.id).label("like_count"))
        .group_by(PostLike.post_id)
        .subquery()
    )
    post_data = (
        db.session.query(
            Post,
            func.coalesce(comment_count_subq.c.comment_count, 0),
            func.coalesce(like_count_subq.c.like_count, 0),
        )
        .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
        .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
        .order_by(Post.timestamp.desc())
        .all()
    )
    posts = [
        {"post": p, "likes": like_count, "comments": comment_count}
        for p, comment_count, like_count in post_data
    ]
    bulletins = [
        {"post": p["post"], "likes": p["likes"], "comments": p["comments"]}
        for p in posts
        if p["post"].author.role == "admin"
    ]
    news = get_rss_highlights()
    events = scrape_events()[:5]
    return render_template(
        "index.html",
        posts=posts[:16],
        bulletins=bulletins[:3],
        news=news,
        events=events,
    )


@blog_bp.route("/all")
def all_posts() -> str:
    page = request.args.get("page", 1, type=int)
    comment_count_subq = (
        db.session.query(Comment.post_id, func.count(Comment.id).label("comment_count"))
        .group_by(Comment.post_id)
        .subquery()
    )
    like_count_subq = (
        db.session.query(PostLike.post_id, func.count(PostLike.id).label("like_count"))
        .group_by(PostLike.post_id)
        .subquery()
    )
    pagination = (
        db.session.query(
            Post,
            func.coalesce(comment_count_subq.c.comment_count, 0),
            func.coalesce(like_count_subq.c.like_count, 0),
        )
        .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
        .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
        .order_by(Post.timestamp.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )
    entries = [
        {"post": p, "likes": like_count, "comments": comment_count}
        for p, comment_count, like_count in pagination.items
    ]
    return render_template("all_posts.html", entries=entries, pagination=pagination)


def populate_replies(comment: Comment) -> None:
    replies = comment.replies.order_by(Comment.timestamp.asc()).all()
    comment.ordered_replies = replies
    for r in replies:
        populate_replies(r)


@blog_bp.route("/post/<slug>", methods=["GET", "POST"])
def view_post(slug: str) -> str:
    post = Post.query.filter_by(slug=slug).first_or_404()
    form = CommentForm(post_id=post.id)
    if form.validate_on_submit():
        author_id = current_user.id if current_user.is_authenticated else None
        guest_name = form.guest_name.data.strip() if not author_id else None
        comment = Comment(
            content=form.content.data,
            author_id=author_id,
            guest_name=guest_name,
            post_id=form.post_id.data,
            parent_id=form.parent_id.data or None,
        )
        db.session.add(comment)
        db.session.commit()
        if current_user.is_authenticated:
            auto_like = CommentLike(user=current_user, comment=comment)
            db.session.add(auto_like)
            db.session.commit()
        if comment.parent_id:
            recipient = comment.parent.author
            verb = "replied to your comment"
        else:
            recipient = post.author
            verb = "commented on your post"
            subs = PostSubscription.query.filter_by(post_id=post.id).all()
            for subscriber in subs:
                if (
                    not current_user.is_authenticated
                    or subscriber.subscriber_id != current_user.id
                ):
                    notif = Notification(
                        recipient_id=subscriber.subscriber_id,
                        actor_id=author_id,
                        guest_name=guest_name,
                        verb="commented on a post you subscribed to",
                        target_type="comment",
                        target_id=comment.id,
                    )
                    db.session.add(notif)
                    attach_email_to_notification(notif)
            db.session.commit()
        if recipient:
            is_self = (
                current_user.is_authenticated and recipient.id == current_user.id
            ) or (not current_user.is_authenticated and recipient is None)
            if not is_self:
                notif = Notification(
                    recipient_id=recipient.id,
                    actor_id=author_id,
                    guest_name=guest_name,
                    verb=verb,
                    target_type="comment",
                    target_id=comment.id,
                )
                db.session.add(notif)
                attach_email_to_notification(notif)
                db.session.commit()
        return redirect(url_for("blog.view_post", slug=slug) + f"#c{comment.id}")
    comments = (
        Comment.query.filter_by(post_id=post.id, parent_id=None)
        .order_by(Comment.timestamp.desc())
        .all()
    )
    for c in comments:
        populate_replies(c)
    return render_template("post_detail.html", post=post, form=form, comments=comments)


@blog_bp.route("/like/post/<int:post_id>", methods=["POST"])
@limiter.limit(
    "20 per day",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def toggle_post_like(post_id):
    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(PostLike(user=current_user, post=post))
        if post.author.id != current_user.id:
            notif = Notification(
                recipient_id=post.author_id,
                actor_id=current_user.id,
                verb="liked your post",
                target_type="post",
                target_id=post.id,
            )
            db.session.add(notif)
    db.session.commit()
    return redirect(request.referrer or url_for("blog.view_post", slug=post.slug))


@blog_bp.route("/like/comment/<int:comment_id>", methods=["POST"])
@limiter.limit(
    "20 per day",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def toggle_comment_like(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    like = CommentLike.query.filter_by(
        user_id=current_user.id, comment_id=comment_id
    ).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(CommentLike(user=current_user, comment=comment))
        if comment.author_id != current_user.id:
            notif = Notification(
                recipient_id=comment.author_id,
                actor_id=current_user.id,
                verb="liked your comment",
                target_type="comment",
                target_id=comment.id,
            )
            db.session.add(notif)
    db.session.commit()
    return redirect(
        request.referrer or url_for("blog.view_post", slug=comment.post.slug)
    )


@blog_bp.route("/create", methods=["GET", "POST"])
@limiter.limit(
    "5 per hour",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def create_post():
    if not current_user.is_contributor():
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post = Post(
            title=form.title.data,
            slug=slugify(form.title.data),
            content=form.content.data,
            author=current_user,
        )
        db.session.add(post)
        db.session.commit()
        auto_like = PostLike(user=current_user, post=post)
        db.session.add(auto_like)
        db.session.commit()
        subs = UserSubscription.query.filter_by(user_id=current_user.id).all()
        for subscriber in subs:
            if subscriber.subscriber_id != current_user.id:
                notif = Notification(
                    recipient_id=subscriber.subscriber_id,
                    actor_id=current_user.id,
                    verb="posted a new article",
                    target_type="post",
                    target_id=post.id,
                )
                db.session.add(notif)
                attach_email_to_notification(notif)
        db.session.commit()
        flash("Post created!", "success")
        return redirect(url_for("blog.view_post", slug=post.slug))
    return render_template("post_form.html", form=form, action="Create")


@blog_bp.route("/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int):
    post: Post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm(obj=post, post_id=post.id)
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        post.updated_at = timestamp()
        post.slug = slugify(post.title)
        flash("Post updated.", "success")
        return redirect(url_for("blog.view_post", slug=post.slug))
    return render_template("post_form.html", form=form, action="Edit")


@blog_bp.route("/delete/<int:post_id>", methods=["POST"])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    is_author = post.author_id == current_user.id
    is_mod = current_user.is_moderator()
    is_admin = current_user.is_admin()
    if not (is_author or is_mod or is_admin):
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("blog.all_posts"))


@blog_bp.route("/user/<username>")
def user_posts(username):
    user = User.query.filter_by(username=username).first_or_404()
    active_tab = request.args.get("tab", "posts")
    page_posts = request.args.get("page", 1, type=int) if active_tab == "posts" else 1
    page_comments = (
        request.args.get("page", 1, type=int) if active_tab == "comments" else 1
    )
    posts_entries = []
    comments_entries = []
    posts_pagination = None
    comments_pagination = None
    if active_tab == "posts":
        posts_pagination = (
            db.session.query(
                Post,
                func.count(Comment.id).label("comment_count"),
                func.count(PostLike.id).label("like_count"),
            )
            .outerjoin(Comment, Comment.post_id == Post.id)
            .outerjoin(PostLike, PostLike.post_id == Post.id)
            .filter(Post.author_id == user.id)
            .group_by(Post.id)
            .order_by(Post.timestamp.desc())
            .paginate(page=page_posts, per_page=10, error_out=False)
        )
        posts_entries = [
            {"post": p, "likes": like_count, "comments": comment_count}
            for p, comment_count, like_count in posts_pagination.items
        ]
    elif active_tab == "comments":
        comments_pagination = (
            Comment.query.filter_by(author_id=user.id)
            .order_by(Comment.timestamp.desc())
            .paginate(page=page_comments, per_page=10, error_out=False)
        )
        comments_entries = comments_pagination.items
    return render_template(
        "user_posts.html",
        user=user,
        active_tab=active_tab,
        posts_entries=posts_entries,
        posts_pagination=posts_pagination,
        comments_entries=comments_entries,
        comments_pagination=comments_pagination,
    )


@blog_bp.route("/comment/remove/<int:comment_id>", methods=["POST"])
@login_required
def remove_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    is_author = comment.author_id == current_user.id
    is_mod = current_user.is_moderator()
    is_admin = current_user.is_admin()
    if not (is_author or is_mod or is_admin):
        abort(403)
    comment.is_removed = True
    if is_admin:
        comment.removed_by = "admin"
    if is_mod:
        comment.removed_by = "moderator"
    else:
        comment.removed_by = "user"
    comment.removed_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("Comment content removed.", "info")
    return redirect(
        request.referrer or url_for("blog.view_post", slug=comment.post.slug)
    )


@blog_bp.route("/search")
def search():
    form = SearchForm(request.args, meta={"csrf": False})
    posts = []
    pagination = None
    if form.validate():
        q = f"%{form.q.data}%"
        page = request.args.get("page", 1, type=int)
        per_page = 10
        query = Post.query.filter(
            or_(Post.title.ilike(q), Post.content.ilike(q))
        ).order_by(Post.timestamp.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
    return render_template("search.html", form=form, posts=posts, pagination=pagination)


@blog_bp.route("/maintenance")
def five_oh_two():
    return render_template("maintenance.html")


@blog_bp.route("/notifications")
@login_required
def notifications():
    tab = request.args.get("tab", "unread")
    page = request.args.get("page", 1, type=int)
    per_page = 20
    q = Notification.query.filter_by(recipient_id=current_user.id)
    if tab == "unread":
        q = q.filter(Notification.read_at == None)
    elif tab == "read":
        q = q.filter(Notification.read_at != None)
    elif tab == "replies":
        q = q.filter(
            Notification.verb.in_(["replied to your comment", "commented on your post"])
        )
    elif tab == "likes":
        q = q.filter(Notification.verb.in_(["liked your comment", "liked your post"]))
    pagination = q.order_by(Notification.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    notifs = pagination.items
    valid_notifs = []
    for n in notifs:
        if n.target_type == "post" and not n.post:
            n.read_at = timestamp()
            continue
        if n.target_type == "comment" and (not n.comment or not n.comment.post):
            n.read_at = timestamp()
            continue
        valid_notifs.append(n)
    if tab == "unread":
        Notification.query.filter(
            Notification.recipient_id == current_user.id,
            Notification.verb.in_(
                ["liked your post", "liked your comment", "posted a new article"]
            ),
            Notification.read_at.is_(None),
        ).update({"read_at": timestamp()})
        db.session.commit()
    return render_template(
        "notifications.html",
        notifications=valid_notifs,
        pagination=pagination,
        active_tab=tab,
    )


@blog_bp.route("/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    notif: Notification = Notification.query.filter_by(
        id=notif_id, recipient_id=current_user.id
    ).first_or_404()
    if notif.read_at is None:
        notif.read_at = timestamp()
        db.session.commit()
    next_url = request.form.get("next") or url_for("blog.notifications")
    return redirect(next_url)


@blog_bp.route("/report", methods=["GET", "POST"])
@limiter.limit(
    "25 per day",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def report():
    if request.method == "GET":
        post_id = request.args.get("post_id", type=int)
        comment_id = request.args.get("comment_id", type=int)
        if not (post_id or comment_id):
            abort(400)
        post_content = Post.query.get(post_id) if post_id else None
        comment_content = Comment.query.get(comment_id) if comment_id else None
        return render_template(
            "report_form.html", post=post_content, comment=comment_content
        )
    post_id = request.form.get("post_id", type=int)
    comment_id = request.form.get("comment_id", type=int)
    reason = request.form.get("reason", "").strip()[:200]
    if not (post_id or comment_id) or not reason:
        flash("Please select something to report, and give a reason." "error")
        return redirect(request.referrer or url_for("blog.all_posts"))
    if comment_id:
        comment = Comment.query.get_or_404(comment_id)
        return_page = lambda: redirect(
            url_for("blog.view_post", slug=comment.post.slug) + f"#c{comment.id}"
        )
    else:
        post = Post.query.get_or_404(post_id)
        return_page = lambda: redirect(url_for("blog.view_post", slug=post.slug))
    existing = Report.query.filter_by(
        reporter_id=current_user.id, post_id=post_id, comment_id=comment_id
    ).first()
    if existing:
        flash("You've already reported this.", "info")
        return return_page()
    rpt = Report(
        reporter_id=current_user.id,
        post_id=post_id,
        comment_id=comment_id,
        reason=reason,
    )
    db.session.add(rpt)
    db.session.commit()
    flash("Report submitted--thank you.", "success")
    return return_page()


def populate_thread(c):
    c.ordered_replies = c.replies.order_by(Comment.timestamp.asc()).all()
    for r in c.ordered_replies:
        populate_thread(r)


@blog_bp.route("/comments/thread/<int:comment_id>", methods=["GET", "POST"])
def comment_thread(comment_id):
    root: Post = Comment.query.get_or_404(comment_id)
    form: CommentForm = CommentForm(post_id=root.post_id, parent_id=root.id)
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            abort(403)
        comment = Comment(
            content=form.content.data,
            author=current_user,
            post_id=form.post_id.data,
            parent_id=form.parent_id.data or None,
        )
        db.session.add(comment)
        db.session.commit()
        auto_like = CommentLike(user=current_user, comment=comment)
        db.session.add(auto_like)
        db.session.commit()
        if comment.parent_id:
            recipient = comment.parent.author
            verb = "replied to your comment"
        else:
            recipient = root.post.author
            verb = "commented on your post"
            subs = PostSubscription.query.filter_by(post_id=root.post.id).all()
            for subscriber in subs:
                if subscriber.subscriber_id != current_user.id:
                    notif = Notification(
                        recipient_id=subscriber.subscriber_id,
                        actor_id=current_user.id,
                        verb="commented on a post you subscribed to",
                        target_type="comment",
                        target_id=comment.id,
                    )
                    db.session.add(notif)
                    attach_email_to_notification(notif)
            db.session.commit()
        if recipient.id != current_user.id:
            notif = Notification(
                recipient_id=recipient.id,
                actor_id=current_user.id,
                verb=verb,
                target_type="comment",
                target_id=comment.id,
            )
            db.session.add(notif)
            attach_email_to_notification(notif)
            db.session.commit()
    populate_thread(root)
    return render_template("comment_thread.html", root=root, form=form)


@blog_bp.route("/comment/<int:comment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_comment(comment_id):
    comment: Comment = Comment.query.get_or_404(comment_id)
    if comment.author_id != current_user.id and not current_user.is_admin():
        abort(403)
    form = CommentEditForm(comment_id=comment.id)
    if form.validate_on_submit():
        comment.content = form.content.data
        comment.mark_edited()
        db.session.commit()
        return redirect(
            url_for("blog.view_post", slug=comment.post.slug) + f"#c{comment.id}"
        )
    form.content.data = comment.content
    return render_template("edit_comment.html", form=form, comment=comment)


def attach_email_to_notification(notif: Notification) -> None:
    db.session.flush()
    if notif.target_type != "comment":
        return
    if not notif.recipient.email_notifications:
        return
    if notif.actor:
        actor_name = notif.actor.username
    else:
        actor_name = notif.guest_name or "Someone"
    comment = notif.comment
    post = comment.post
    link = url_for("blog.view_post", slug=post.slug, _external=True) + f"#c{comment.id}"
    subject = f"{actor_name} {notif.verb}"
    text_body = render_template(
        "emails/comment_notification.txt",
        actor=actor_name,
        verb=notif.verb,
        post=post,
        comment=comment,
        link=link,
    )
    html_body = render_template(
        "emails/comment_notification.html",
        actor=actor_name,
        verb=notif.verb,
        post=post,
        comment=comment,
        link=link,
    )
    app.config["MAIL_DEFAULT_SENDER"] = MAIL_NOTIFICATION
    msg = Message(
        subject=subject,
        recipients=[notif.recipient.email],
        body=text_body,
        html=html_body,
    )
    app.mail.send(msg)
