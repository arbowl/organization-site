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
from wtforms.validators import ValidationError

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
    Tag,
    PostLink,
    SplinterItem,
)
from app.forms import PostForm, CommentForm, SearchForm, CommentEditForm, NewsletterForm
from app.utils import scrape_events, color_from_slug
from app.email_utils import send_email_with_config

blog_bp: Blueprint = Blueprint("blog", __name__)
timestamp = partial(datetime.now, timezone.utc)


@blog_bp.route("/")
def index() -> str:
    """The landing page of the site"""
    comment_count_subq, like_count_subq = get_comment_like_subqueries()
    
    post_data = (
        db.session.query(
            Post,
            func.coalesce(comment_count_subq.c.comment_count, 0),
            func.coalesce(like_count_subq.c.like_count, 0),
        )
        .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
        .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
        .order_by(Post.published_at.desc())
        .filter(Post.is_draft == False)
        .all()
    )
    
    posts = create_post_data_with_counts(post_data)
    bulletins = [
        {"post": p["post"], "likes": p["likes"], "comments": p["comments"]}
        for p in posts
        if p["post"].author.role == "admin"
    ]
    events = scrape_events()[:12]
    
    # Get active discussion threads for the front page
    discussion_threads = get_active_discussion_threads()
    
    # Get hot bills for the front page
    hot_bills = get_hot_bills()
    
    return render_template(
        "index.html",
        posts=posts[:16],
        bulletins=bulletins[:3],
        events=events,
        discussion_threads=discussion_threads,
        hot_bills=hot_bills,
        newsletter_form=NewsletterForm(),
    )


def get_active_discussion_threads():
    """Find the most engaging discussion threads based on post connections"""
    try:
        # Use subqueries to get accurate counts (same pattern as index route)
        comment_count_subq, like_count_subq = get_comment_like_subqueries()
        
        # Get posts with the most connections and accurate engagement counts
        thread_candidates = (
            db.session.query(
                Post,
                func.count(PostLink.id).label("connection_count"),
                func.coalesce(comment_count_subq.c.comment_count, 0).label("comment_count"),
                func.coalesce(like_count_subq.c.like_count, 0).label("like_count"),
            )
            .outerjoin(
                PostLink,
                or_(
                    PostLink.src_post_id == Post.id,
                    PostLink.dst_post_id == Post.id,
                ),
            )
            .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
            .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
            .filter(Post.is_draft == False)
            .group_by(Post.id)
            .having(func.count(PostLink.id) > 0)  # Only posts with connections
            .order_by(
                func.count(PostLink.id).desc(),
                func.coalesce(comment_count_subq.c.comment_count, 0).desc(),
                func.coalesce(like_count_subq.c.like_count, 0).desc(),
            )
            .limit(3)
            .all()
        )

        threads = []
        for post, connections, comments, likes in thread_candidates:
            try:
                # Find related posts in this thread (both roots and branches)
                related_posts = (
                    db.session.query(Post)
                    .join(
                        PostLink,
                        or_(
                            PostLink.src_post_id == Post.id,
                            PostLink.dst_post_id == Post.id,
                        ),
                    )
                    .filter(
                        or_(
                            PostLink.src_post_id == post.id,
                            PostLink.dst_post_id == post.id,
                        )
                    )
                    .filter(Post.is_draft == False)
                    .filter(Post.id != post.id)  # Exclude the main post
                    .order_by(Post.published_at.desc())
                    .limit(5)
                    .all()
                )

                # Calculate thread depth and engagement
                # thread_depth should represent actual connections, not limited subset
                thread_depth = connections  # Use actual connection count instead of limited related_posts length
                total_engagement = comments + likes
                
                # Get the most recent splinter if this post has one
                splinter = (
                    db.session.query(Post)
                    .filter(Post.is_splinter == True, Post.target_post_id == post.id)
                    .filter(Post.is_draft == False)
                    .order_by(Post.published_at.desc())
                    .first()
                )

                threads.append({
                    "main_post": post,
                    "related_posts": related_posts,
                    "connection_count": connections,
                    "total_engagement": total_engagement,
                    "thread_depth": thread_depth,
                    "splinter": splinter,
                    "comment_count": comments,
                    "like_count": likes,
                })
            except Exception as e:
                # Log error but continue with other threads
                print(f"Error processing thread for post {post.id}: {e}")
                continue

        return threads
    except Exception as e:
        # If there's an error, return empty list to avoid breaking the page
        print(f"Error getting discussion threads: {e}")
        return []


def get_hot_bills():
    """Get bills with the most recent comments for the front page"""
    try:
        from app.models import Bill, Comment
        from sqlalchemy import func, case
        
        # Get bills with two-tier ranking:
        # 1. Bills with recent comments (sorted by most recent comment timestamp)
        # 2. Bills without comments (sorted by creation date, newest first)
        bill_data = (
            db.session.query(
                Bill,
                func.max(Comment.timestamp).label("latest_comment_time"),
                func.count(Comment.id).label("comment_count"),
                # Create a ranking field: 0 for bills with comments, 1 for bills without
                case(
                    (func.count(Comment.id) > 0, 0),
                    else_=1
                ).label("has_comments_rank")
            )
            .outerjoin(Comment, Bill.id == Comment.bill_id)
            .group_by(Bill.id)
            .order_by(
                # First: bills with comments (rank 0) before bills without (rank 1)
                case(
                    (func.count(Comment.id) > 0, 0),
                    else_=1
                ),
                # Second: within each group, sort by most recent comment time (for bills with comments)
                func.max(Comment.timestamp).desc().nulls_last(),
                # Third: for bills without comments, sort by creation date (newest first)
                Bill.created_at.desc()
            )
            .limit(10)  # Show 10 in dropdown
            .all()
        )
        
        # Return in same format as posts: list of dictionaries
        hot_bills = [
            {"bill": bill, "comments": comment_count, "latest_comment": latest_comment_time}
            for bill, latest_comment_time, comment_count, has_comments_rank in bill_data
        ]
        
        return hot_bills
    except Exception as e:
        # If there's an error, return empty list to avoid breaking the page
        print(f"Error getting hot bills: {e}")
        return []


@blog_bp.route("/all")
def all_posts() -> str:
    page = request.args.get("page", 1, type=int)
    raw_tags = (request.args.get("tags") or "").strip()
    tag_slugs = [slugify(t.strip()) for t in raw_tags.split(",") if t.strip()]
    
    comment_count_subq, like_count_subq = get_comment_like_subqueries()
    
    base = (
        db.session.query(
            Post,
            func.coalesce(comment_count_subq.c.comment_count, 0),
            func.coalesce(like_count_subq.c.like_count, 0),
        )
        .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
        .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
        .filter(Post.is_draft == False)
    )
    if tag_slugs:
        for s in tag_slugs:
            base = base.filter(Post.tags.any(Tag.slug == s))

    base = base.order_by(Post.published_at.desc())
    pagination = base.paginate(page=page, per_page=10, error_out=False)
    entries = create_post_data_with_counts(pagination.items)
    
    recent_comments = Comment.query.order_by(Comment.timestamp.desc()).limit(5).all()
    
    tag_counts = db.session.query(Tag).order_by(Tag.name).all()
    trending_tags = []
    for t in tag_counts:
        try:
            cnt = t.posts.count()
        except Exception:
            cnt = Post.query.filter(Post.tags.any(Tag.id == t.id)).count()
        trending_tags.append((t, cnt))
    trending_tags.sort(key=lambda x: x[1], reverse=True)
    trending_tags = trending_tags[:15]
    
    return render_template(
        "all_posts.html",
        entries=entries,
        pagination=pagination,
        tag_slugs=tag_slugs,
        recent_comments=recent_comments,
        trending_tags=trending_tags,
        newsletter_form=NewsletterForm(),
    )


def populate_replies(comment: Comment) -> None:
    replies = comment.replies.order_by(Comment.timestamp.asc()).all()
    comment.ordered_replies = replies
    for r in replies:
        populate_replies(r)


@blog_bp.route("/post/<slug>", methods=["GET", "POST"])
def view_post(slug: str) -> str:
    post = Post.query.filter_by(slug=slug).first_or_404()
    if post.is_draft and (not current_user.is_authenticated or post.author != current_user):
        abort(404)
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
            db.session.add(CommentLike(user=current_user, comment=comment))
            db.session.commit()
        pending_notifs = []
        recipient = None
        verb = None
        if comment.parent_id:
            recipient = getattr(comment.parent, "author", None)
            verb = "replied to your comment"
        else:
            recipient = post.author
            verb = "commented on your post"
            subs = PostSubscription.query.filter_by(post_id=post.id).all()
            for subscriber in subs:
                if (not current_user.is_authenticated) or (
                    subscriber.subscriber_id != current_user.id
                ):
                    pending_notifs.append(
                        Notification(
                            recipient_id=subscriber.subscriber_id,
                            actor_id=author_id,
                            guest_name=guest_name,
                            verb="commented on a post you subscribed to",
                            target_type="comment",
                            target_id=comment.id,
                        )
                    )
        if recipient is not None:
            is_self = (
                current_user.is_authenticated and recipient.id == current_user.id
            ) or (not current_user.is_authenticated and recipient is None)
            if not is_self:
                pending_notifs.append(
                    Notification(
                        recipient_id=recipient.id,
                        actor_id=author_id,
                        guest_name=guest_name,
                        verb=verb,
                        target_type="comment",
                        target_id=comment.id,
                    )
                )
        if pending_notifs:
            for n in pending_notifs:
                db.session.add(n)
            db.session.flush()
            for n in pending_notifs:
                attach_email_to_notification(n)
            db.session.commit()

        return redirect(url_for("blog.view_post", slug=slug) + f"#c{comment.id}")

    comments = (
        Comment.query.filter_by(post_id=post.id, parent_id=None)
        .order_by(Comment.timestamp.desc())
        .all()
    )
    for c in comments:
        populate_replies(c)
    try:
        trending_tags = (
            db.session.query(Tag, func.count(Post.id).label("cnt"))
            .join(Tag.posts)
            .group_by(Tag.id)
            .order_by(func.count(Post.id).desc())
            .limit(15)
            .all()
        )
    except Exception:
        trending_tags = []
        for t in Tag.query.order_by(Tag.name).all():
            try:
                cnt = t.posts.count()
            except Exception:
                cnt = Post.query.filter(Post.tags.any(Tag.id == t.id)).count()
            trending_tags.append((t, cnt))
        trending_tags.sort(key=lambda x: x[1], reverse=True)
        trending_tags = trending_tags[:15]
    recent_comments = Comment.query.order_by(Comment.timestamp.desc()).limit(5).all()
    # Roots: posts THIS post references (outgoing edges)
    roots = (
        db.session.query(Post)
        .join(PostLink, PostLink.dst_post_id == Post.id)
        .filter(PostLink.src_post_id == post.id)
        .order_by(Post.published_at.desc())
        .filter(Post.is_draft == False)
        .limit(5)
        .all()
    )
    # Branches: posts that reference THIS post (incoming edges)
    branches = (
        db.session.query(Post)
        .join(PostLink, PostLink.src_post_id == Post.id)
        .filter(PostLink.dst_post_id == post.id)
        .order_by(Post.published_at.desc())
        .filter(Post.is_draft == False)
        .limit(5)
        .all()
    )
    splinters = (
        db.session.query(Post)
        .filter(Post.is_splinter == True, Post.target_post_id == post.id)
        .order_by(Post.published_at.desc())
        .filter(Post.is_draft == False)
        .limit(2)
        .all()
    )
    return render_template(
        "post_detail.html",
        post=post,
        trending_tags=trending_tags,
        form=form,
        comments=comments,
        recent_comments=recent_comments,
        roots=roots,
        branches=branches,
        splinters=splinters,
    )


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
    comment: Comment = Comment.query.get_or_404(comment_id)
    like = CommentLike.query.filter_by(
        user_id=current_user.id, comment_id=comment_id
    ).first()
    if like:
        db.session.delete(like)
    else:
        db.session.add(CommentLike(user=current_user, comment=comment))
        if comment.author_id != current_user.id and comment.author is not None:
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
    "10 per hour",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def create_post():
    if not current_user.is_contributor():
        return render_template("contributing.html")
    tag_queries = Tag.query.order_by(Tag.name).all() if request.method == "GET" else []
    form = PostForm()
    if form.validate_on_submit():
        is_draft = bool(form.save_draft.data)
        post = Post(
            title=form.title.data,
            slug=slugify(form.title.data),
            content=form.content.data,
            author=current_user,
            timestamp=timestamp(),
            is_draft=is_draft,
        )
        # Set published_at for direct posts (not drafts)
        if not is_draft:
            post.published_at = timestamp()
        db.session.add(post)
        try:
            for name in form.clean_tags():
                post.tags.append(get_or_create_tag(name))
        except ValidationError as e:
            form.tags.errors.append(str(e))
            flash(str(e), "error")
            return (
                render_template(
                    "post_form.html",
                    form=form,
                    tag_queries=tag_queries,
                    action="Create",
                ),
                400,
            )
        db.session.commit()
        if is_draft:
            flash("Draft saved.", "info")
            return redirect(url_for("blog.list_drafts"))
        existing_like = PostLike.query.filter_by(
            user_id=current_user.id, post_id=post.id
        ).first()
        if not existing_like:
            db.session.add(PostLike(user=current_user, post=post))
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
    return render_template(
        "post_form.html", form=form, tag_queries=tag_queries, action="Create"
    )

@blog_bp.route("/edit/<int:post_id>", methods=["GET", "POST"])
@login_required
def edit_post(post_id: int):
    post: Post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    tag_queries = Tag.query.order_by(Tag.name).all() if request.method == "GET" else []
    form: PostForm = PostForm(obj=post, post_id=post.id)
    if form.validate_on_submit():
        was_draft = bool(post.is_draft)
        will_be_draft = bool(form.save_draft.data)
        will_publish_now = was_draft and not will_be_draft
        post.title = form.title.data
        post.content = form.content.data
        post.slug = slugify(post.title)
        post.is_draft = will_be_draft
        if will_publish_now and post.published_at is None:
            post.published_at = timestamp()
        elif will_publish_now and post.published_at is not None:
            post.updated_at = timestamp()
        elif (not was_draft) and (not will_be_draft):
            post.updated_at = timestamp()
        try:
            new_tags = [get_or_create_tag(n) for n in form.clean_tags()]
        except ValidationError as e:
            form.tags.errors.append(str(e))
            flash(str(e), "error")
            return (
                render_template(
                    "post_form.html", form=form, tag_queries=tag_queries, action="Edit"
                ),
                400,
            )
        post.tags = new_tags
        db.session.commit()
        if will_publish_now:
            existing_like = PostLike.query.filter_by(
                user_id=current_user.id, post_id=post.id
            ).first()
            if not existing_like:
                db.session.add(PostLike(user=current_user, post=post))
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
            flash("Post published!", "success")
            return redirect(url_for("blog.view_post", slug=post.slug))
        if post.is_draft:
            flash("Draft updated.", "info")
            return redirect(url_for("blog.list_drafts"))
        else:
            flash("Post updated.", "success")
            return redirect(url_for("blog.view_post", slug=post.slug))
    if request.method == "GET":
        form.tags.data = ", ".join([t.name for t in post.tags.order_by(Tag.name).all()])
    return render_template(
        "post_form.html", form=form, tag_queries=tag_queries, action="Edit"
    )


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
        comment_count_subq, like_count_subq = get_comment_like_subqueries()
        
        posts_pagination = (
            db.session.query(
                Post,
                func.coalesce(comment_count_subq.c.comment_count, 0),
                func.coalesce(like_count_subq.c.like_count, 0),
            )
            .outerjoin(comment_count_subq, Post.id == comment_count_subq.c.post_id)
            .outerjoin(like_count_subq, Post.id == like_count_subq.c.post_id)
            .filter(Post.is_draft == False)
            .filter(Post.author_id == user.id)
            .order_by(Post.published_at.desc())
            .paginate(page=page_posts, per_page=10, error_out=False)
        )
        posts_entries = create_post_data_with_counts(posts_pagination.items)
    elif active_tab == "comments":
        comments_pagination = (
            Comment.query.filter_by(author_id=user.id)
            .order_by(Comment.timestamp.desc())
            .paginate(page=page_comments, per_page=10, error_out=False)
        )
        comments_entries = comments_pagination.items
    
    # Create BioForm with available tags for the current user
    from app.forms import BioForm
    from app.models import Tag
    
    bio_form = None
    if current_user.is_authenticated and current_user.username == user.username:
        all_tags = Tag.query.order_by(Tag.name).all()
        bio_form = BioForm()
        bio_form.favorite_tags.choices = [(tag.id, tag.name) for tag in all_tags]
        # Set current favorite tags
        if user.favorite_tags:
            bio_form.favorite_tags.data = user.favorite_tags
    
    return render_template(
        "user_posts.html",
        user=user,
        active_tab=active_tab,
        posts_entries=posts_entries,
        posts_pagination=posts_pagination,
        comments_entries=comments_entries,
        comments_pagination=comments_pagination,
        bio_form=bio_form,
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
    elif is_mod:
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
    if form.validate() and (form.q.data or "").strip():
        q = f"%{form.q.data}%"
        page = request.args.get("page", 1, type=int)
        per_page = 10
        query = Post.query.filter(
            or_(Post.title.ilike(q), Post.content.ilike(q))
        ).filter(Post.is_draft == False).order_by(Post.published_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        posts = pagination.items
    recent_comments = Comment.query.order_by(Comment.timestamp.desc()).limit(5).all()
    try:
        trending_tags = (
            db.session.query(Tag, func.count(Post.id).label("cnt"))
            .join(Tag.posts)
            .group_by(Tag.id)
            .order_by(func.count(Post.id).desc())
            .limit(15)
            .all()
        )
    except Exception:
        trending_tags = []
        for t in Tag.query.order_by(Tag.name).all():
            try:
                cnt = t.posts.count()
            except Exception:
                cnt = Post.query.filter(Post.tags.any(Tag.id == t.id)).count()
            trending_tags.append((t, cnt))
        trending_tags.sort(key=lambda x: x[1], reverse=True)
        trending_tags = trending_tags[:15]
    return render_template(
        "search.html",
        form=form,
        posts=posts,
        pagination=pagination,
        recent_comments=recent_comments,
        trending_tags=trending_tags,
        newsletter_form=NewsletterForm(),
    )


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
            Notification.verb.in_([
                "replied to your comment",
                "commented on your post",
            ])
        )
    elif tab == "likes":
        q = q.filter(Notification.verb.in_(["liked your comment", "liked your post"]))
    pagination = q.order_by(Notification.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    notifs: list[Notification] = pagination.items
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
                [
                    "liked your post",
                    "liked your comment",
                    "posted a new article",
                    "posted a new splinter",
                    "splintered your post",
                ]
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


@blog_bp.route("/post/<slug>/splinter/new", methods=["GET", "POST"])
@limiter.limit(
    "10 per hour",
    key_func=lambda: current_user.id if current_user.is_authenticated else "anon",
)
@login_required
def new_splinter(slug):
    if not current_user.is_contributor():
        return render_template("contributing.html")
    target = Post.query.filter_by(slug=slug).first_or_404()
    form = PostForm()
    if form.validate_on_submit():
        is_draft = bool(form.save_draft.data)
        spl = Post(
            title=form.title.data,
            slug=slugify(form.title.data),
            content=form.content.data,
            author=current_user,
            timestamp=timestamp(),
            is_splinter=True,
            target_post_id=target.id,
            is_draft=is_draft,
        )
        # Set published_at for direct splinter posts (not drafts)
        if not is_draft:
            spl.published_at = timestamp()
        db.session.add(spl)
        with db.session.no_autoflush:
            try:
                for name in form.clean_tags():
                    spl.tags.append(get_or_create_tag(name))
            except ValidationError as e:
                form.tags.errors.append(str(e))
                flash(str(e), "error")
                return (
                    render_template(
                        "post_form.html",
                        form=form,
                        tag_queries=Tag.query.order_by(Tag.name).all(),
                        action="Splinter",
                    ),
                    400,
                )
        db.session.commit()
        if is_draft:
            flash("Splinter draft saved.", "info")
            return redirect(url_for("blog.list_drafts"))
        existing_like = PostLike.query.filter_by(
            user_id=current_user.id, post_id=spl.id
        ).first()
        if not existing_like:
            db.session.add(PostLike(user=current_user, post=spl))
        if target.author_id != current_user.id:
            notif = Notification(
                recipient_id=target.author_id,
                actor_id=current_user.id,
                verb="splintered your post",
                target_type="post",
                target_id=spl.id,
            )
            db.session.add(notif)
            attach_email_to_notification(notif)
        subs = UserSubscription.query.filter_by(user_id=current_user.id).all()
        for subscriber in subs:
            if subscriber.subscriber_id != current_user.id:
                notif = Notification(
                    recipient_id=subscriber.subscriber_id,
                    actor_id=current_user.id,
                    verb="posted a new splinter",
                    target_type="post",
                    target_id=spl.id,
                )
                db.session.add(notif)
                attach_email_to_notification(notif)
        db.session.commit()
        flash("Splinter created. Now add your rebuttal items below.", "info")
        return redirect(url_for("blog.edit_splinter_items", splinter_slug=spl.slug))
    return render_template(
        "post_form.html",
        form=form,
        tag_queries=Tag.query.order_by(Tag.name).all(),
        action="Splinter",
    )

@blog_bp.route("/splinter/<splinter_slug>/items", methods=["GET", "POST"])
@login_required
def edit_splinter_items(splinter_slug):
    spl = Post.query.filter_by(slug=splinter_slug, is_splinter=True).first_or_404()
    if spl.author_id != current_user.id and not current_user.is_moderator():
        abort(403)
    if request.method == "POST":
        items = request.json or {}
        items_list = items.get("items", [])
        for it in items_list:
            si = SplinterItem(
                splinter_post_id=spl.id,
                target_post_id=spl.target_post_id,
                quote_text=(it.get("quote_text") or "")[:2000],
                quote_html=it.get("quote_html"),
                selector_json=it.get("selector_json"),
                label=(it.get("label") or "claim")[:32],
                summary=(it.get("summary") or "")[:280],
                body=it.get("body"),
            )
            db.session.add(si)
        db.session.commit()
        return {"ok": True}
    target = spl.target_post
    return render_template("splinter_items.html", splinter=spl, target=target)


@blog_bp.route("/edit/splinter/<slug>", methods=["GET", "POST"])
@login_required
def edit_splinter(slug):
    splinter = Post.query.filter_by(slug=slug, is_splinter=True).first_or_404()
    if splinter.author != current_user:
        abort(403)
    tag_queries = Tag.query.order_by(Tag.name).all() if request.method == "GET" else []
    form = PostForm(obj=splinter, post_id=splinter.id)
    if form.validate_on_submit():
        was_draft = bool(splinter.is_draft)
        will_be_draft = bool(form.save_draft.data)
        will_publish_now = was_draft and not will_be_draft
        splinter.title = form.title.data
        splinter.content = form.content.data
        splinter.slug = slugify(form.title.data)
        splinter.is_draft = will_be_draft
        if not will_publish_now:
            splinter.updated_at = timestamp()
        try:
            new_tags = [get_or_create_tag(n) for n in form.clean_tags()]
        except ValidationError as e:
            form.tags.errors.append(str(e))
            flash(str(e), "error")
            return (
                render_template(
                    "post_form.html", form=form, tag_queries=tag_queries, action="Edit"
                ),
                400,
            )
        splinter.tags = new_tags
        db.session.commit()
        if will_publish_now:
            existing_like = PostLike.query.filter_by(
                user_id=current_user.id, post_id=splinter.id
            ).first()
            if not existing_like:
                db.session.add(PostLike(user=current_user, post=splinter))
            target = splinter.target_post
            if target and target.author_id != current_user.id:
                notif = Notification(
                    recipient_id=target.author_id,
                    actor_id=current_user.id,
                    verb="splintered your post",
                    target_type="post",
                    target_id=splinter.id,
                )
                db.session.add(notif)
                attach_email_to_notification(notif)
            subs = UserSubscription.query.filter_by(user_id=current_user.id).all()
            for subscriber in subs:
                if subscriber.subscriber_id != current_user.id:
                    notif = Notification(
                        recipient_id=subscriber.subscriber_id,
                        actor_id=current_user.id,
                        verb="posted a new splinter",
                        target_type="post",
                        target_id=splinter.id,
                    )
                    db.session.add(notif)
                    attach_email_to_notification(notif)
            db.session.commit()
            flash("Splinter published! Now add your rebuttal items below.", "success")
            return redirect(
                url_for("blog.edit_splinter_items", splinter_slug=splinter.slug)
            )
        if splinter.is_draft:
            flash("Splinter draft updated.", "info")
            return redirect(url_for("blog.list_drafts"))
        else:
            flash("Splinter post updated.", "success")
            return redirect(
                url_for("blog.edit_splinter_items", splinter_slug=splinter.slug)
            )
    if request.method == "GET":
        form.tags.data = ", ".join(
            [t.name for t in splinter.tags.order_by(Tag.name).all()]
        )
    return render_template(
        "post_form.html",
        form=form,
        tag_queries=tag_queries,
        action="Splinter",
    )


@blog_bp.route("/splinter/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_splinter_item(item_id):
    item = SplinterItem.query.get_or_404(item_id)
    if (
        item.splinter_post.author_id != current_user.id
        and not current_user.is_moderator()
    ):
        abort(403)
    db.session.delete(item)
    db.session.commit()
    flash("Rebuttal item deleted.", "success")
    return redirect(
        url_for("blog.edit_splinter_items", splinter_slug=item.splinter_post.slug)
    )


@blog_bp.route("/tag/<slug>")
def tag_view(slug):
    return redirect(url_for("blog.all_posts", tags=slug))


@blog_bp.route("/post/<slug>/references")
def post_references(slug: str):
    post = Post.query.filter_by(slug=slug).first_or_404()
    kind = request.args.get("type", "both").lower()
    page_roots = request.args.get("page_roots", 1, type=int)
    page_branches = request.args.get("page_branches", 1, type=int)
    page_splinters = request.args.get("page_splinters", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    roots_q = (
        db.session.query(Post)
        .join(PostLink, PostLink.dst_post_id == Post.id)
        .filter(PostLink.src_post_id == post.id)
        .filter(Post.is_draft == False)
        .order_by(Post.published_at.desc())
    )
    branches_q = (
        db.session.query(Post)
        .join(PostLink, PostLink.src_post_id == Post.id)
        .filter(PostLink.dst_post_id == post.id)
        .filter(Post.is_draft == False)
        .order_by(Post.published_at.desc())
    )
    splinters_q = (
        db.session.query(Post)
        .filter(Post.is_splinter == True, Post.target_post_id == post.id)
        .filter(Post.is_draft == False)
        .order_by(Post.published_at.desc())
    )
    roots_pagination = (
        roots_q.paginate(page=page_roots, per_page=per_page, error_out=False)
        if kind in ("roots", "both")
        else None
    )
    branches_pagination = (
        branches_q.paginate(page=page_branches, per_page=per_page, error_out=False)
        if kind in ("branches", "both")
        else None
    )
    splinters_pagination = (
        splinters_q.paginate(page=page_splinters, per_page=per_page, error_out=False)
        if kind in ("splinters", "both")
        else None
    )
    return render_template(
        "post_references.html",
        post=post,
        kind=kind,
        roots_pagination=roots_pagination,
        branches_pagination=branches_pagination,
        splinters_pagination=splinters_pagination,
        roots_count=roots_q.count(),
        branches_count=branches_q.count(),
        splinters_count=splinters_q.count(),
        per_page=per_page,
    )


@blog_bp.route("/drafts")
@login_required
def list_drafts():
    drafts = Post.query.filter_by(author_id=current_user.id, is_draft=True).order_by(Post.timestamp.desc()).all()
    return render_template("drafts.html", drafts=drafts)


@blog_bp.route("/draft/<slug>/preview")
def preview_draft(slug):
    """Preview a draft post."""
    post = Post.query.filter_by(slug=slug, is_draft=True).first_or_404()
    if post.author != current_user:
        abort(403)
    return render_template(
        "preview.html",
        post=post,
    )


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
        user=notif.recipient,
    )
    html_body = render_template(
        "emails/comment_notification.html",
        actor=actor_name,
        verb=notif.verb,
        post=post,
        comment=comment,
        link=link,
        user=notif.recipient,
    )
    
    success = send_email_with_config(
        email_type="notification",
        subject=subject,
        recipients=[notif.recipient.email],
        text_body=text_body,
        html_body=html_body
    )
    
    if not success:
        app.logger.error(f"Failed to send notification email to {notif.recipient.email}")


def get_or_create_tag(name: str) -> Tag:
    slug = slugify(name)
    tag = Tag.query.filter_by(slug=slug).first()
    if tag:
        return tag
    tag = Tag(name=name, slug=slug, color_hex=color_from_slug(slug))
    db.session.add(tag)
    return tag


def create_post_data_with_counts(query_results):
    """
    Standardized function to convert query results into post data dictionaries.
    Takes query results (list of tuples with Post, comment_count, like_count) 
    and returns a list of dictionaries with 'post', 'likes', 'comments', and 'tags' keys.
    """
    entries = [
        {"post": p, "likes": like_count, "comments": comment_count}
        for p, comment_count, like_count in query_results
    ]
    
    # Add sorted tags to each entry
    for entry in entries:
        entry["tags"] = sorted(entry["post"].tags, key=lambda t: t.name.lower())
    
    return entries


def get_comment_like_subqueries():
    """
    Returns the standard comment and like count subqueries used across the app.
    """
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
    return comment_count_subq, like_count_subq


def attach_sorted_tags(entries, limit):
    for entry in entries[:limit]:
        entry["tags"] = sorted(entry["post"].tags, key=lambda t: t.name.lower())

