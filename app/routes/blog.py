"""Blog"""

from datetime import datetime, timezone
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from slugify import slugify
from sqlalchemy import func

from app import db
from app.models import Post, User, Comment, PostLike, CommentLike
from app.forms import PostForm, CommentForm
from app.utils import get_rss_highlights, roles_required, scrape_events

blog_bp = Blueprint("blog", __name__)


@blog_bp.route("/")
def index():
    post_data = (
        db.session.query(
            Post,
            func.count(Comment.id).label("comment_count"),
            func.count(PostLike.id).label("like_count"),
        )
        .outerjoin(Comment, Comment.post_id == Post.id)
        .outerjoin(PostLike, PostLike.post_id == Post.id)
        .group_by(Post.id)
        .order_by(Post.timestamp.desc())
        .limit(5)
        .all()
    )
    
    posts = [{
        "post": p,
        "likes": like_count,
        "comments": comment_count
    } for p, comment_count, like_count in post_data]
    
    bulletins = [{
        "post": p["post"],
        "likes": p["likes"],
        "comments": p["comments"]
    } for p in posts if p["post"].author.role == "admin"][:5]
    
    news = get_rss_highlights()
    events = scrape_events()[:5]
    return render_template("index.html", posts=posts, bulletins=bulletins, news=news, events=events)


@blog_bp.route("/all")
def all_posts():
    page = request.args.get("page", 1, type=int)
    pagination = (
        db.session.query(
            Post,
            func.count(Comment.id).label("comment_count"),
            func.count(PostLike.id).label("like_count"),
        )
        .outerjoin(Comment, Comment.post_id == Post.id)
        .outerjoin(PostLike, PostLike.post_id == Post.id)
        .group_by(Post.id)
        .order_by(Post.timestamp.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )
    entries = [{
        "post": p,
        "likes": like_count,
        "comments": comment_count
    } for p, comment_count, like_count in pagination.items]
    return render_template("all_posts.html", entries=entries, pagination=pagination)


def populate_replies(comment):
    replies = comment.replies.order_by(Comment.timestamp.asc()).all()
    comment.ordered_replies = replies
    for r in replies:
        populate_replies(r)


@blog_bp.route("/post/<slug>", methods=["GET", "POST"])
def view_post(slug):
    post = Post.query.filter_by(slug=slug).first_or_404()
    form = CommentForm(post_id=post.id)
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            abort(403)
        comment = Comment(
            content = form.content.data,
            author = current_user,
            post_id = form.post_id.data,
            parent_id = form.parent_id.data or None
        )
        db.session.add(comment)
        db.session.commit()
        return redirect(url_for("blog.view_post", slug=slug) + f"#c{comment.id}")
    comments = (Comment.query.filter_by(post_id=post.id, parent_id=None).order_by(Comment.timestamp.desc()).all())
    for c in comments:
        populate_replies(c)
    return render_template("post_detail.html", post=post, form=form, comments=comments)


@blog_bp.route("/like/post/<int:post_id>", methods=["POST"])
@login_required
def toggle_post_like(post_id):
    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(PostLike(user=current_user, post=post))
    db.session.commit()
    return redirect(request.referrer or url_for("blog.view_post", slug=post.slug))


@blog_bp.route("/like/comment/<int:comment_id>", methods=["POST"])
@login_required
def toggle_comment_like(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    like = CommentLike.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(CommentLike(user=current_user, comment=comment))
    db.session.commit()
    return redirect(request.referrer or url_for("blog.view_post", slug=comment.post.slug))


@blog_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_post():
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
        flash("Post created!", "success")
        return redirect(url_for("blog.view_post", slug=post.slug))
    return render_template("post_form.html", form=form, action="Create")


@blog_bp.route("/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm(obj=post)
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = form.content.data
        db.session.commit()
        flash("Post updated.", "success")
        return redirect(url_for("blog.view_post", slug=post.slug))
    return render_template("post_form.html", form=form, action="Edit")


@blog_bp.route("/delete/<int:post_id>", methods=["POST"])
@roles_required("moderator", "admin")
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("blog.all_posts"))


@blog_bp.route("/user/<username>")
def user_posts(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get("page", 1, type=int)
    pagination = (
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
        .paginate(page=page, per_page=10, error_out=False)
    )
    entries = [{
        "post": p,
        "likes": like_count,
        "comments": comment_count
    } for p, comment_count, like_count in pagination.items]
    return render_template("user_posts.html", user=user, entries=entries, pagination=pagination)


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
    return redirect(request.referrer or url_for("blog.view_post", slug=comment.post.slug))
