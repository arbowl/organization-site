from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from app.models import Bill, Comment, db
from app.forms import BillCommentForm
from datetime import datetime, timezone

bills_bp = Blueprint("bills", __name__)


def get_bill_by_slug(bill_slug):
    """Helper function to find a bill by its slug"""
    for bill in Bill.query.all():
        if bill.slug == bill_slug:
            return bill
    return None


def populate_replies(comment: Comment) -> None:
    """Populate nested replies for a comment (reused from blog.py)"""
    replies = comment.replies.order_by(Comment.timestamp.asc()).all()
    comment.ordered_replies = replies
    for r in replies:
        populate_replies(r)


@bills_bp.route("/bills/<bill_slug>", methods=["GET", "POST"])
def view_bill(bill_slug):
    """Display a specific bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    # Create form for inline commenting
    from app.forms import BillCommentForm
    form = BillCommentForm()
    
    # Handle comment submission (reused from blog.py)
    if form.validate_on_submit():
        author_id = current_user.id if current_user.is_authenticated else None
        guest_name = form.guest_name.data.strip() if not author_id else None
        comment = Comment(
            content=form.content.data,
            author_id=author_id,
            guest_name=guest_name,
            bill_id=bill.id,
            parent_id=form.parent_id.data or None,
        )
        db.session.add(comment)
        db.session.commit()
        
        flash("Comment added successfully!", "success")
        return redirect(url_for("bills.view_bill", bill_slug=bill_slug))
    
    # Get comments for this bill
    comments = Comment.query.filter_by(bill_id=bill.id, parent_id=None).order_by(Comment.timestamp.desc()).all()
    
    # Populate nested replies for each comment
    for comment in comments:
        populate_replies(comment)
    
    # Get recent comments for sidebar (both bill comments and regular post comments)
    recent_bill_comments = Comment.query.order_by(Comment.timestamp.desc()).limit(5).all()
    
    # Get trending tags for sidebar
    from sqlalchemy import func
    from app.models import Tag, Post
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
    
    return render_template("bills/view.html", 
                         bill=bill, 
                         comments=comments, 
                         form=form,
                         recent_bill_comments=recent_bill_comments,
                         trending_tags=trending_tags)


@bills_bp.route("/bills/<bill_slug>/comment", methods=["GET", "POST"])
def add_comment(bill_slug):
    """Add a comment to a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    form = BillCommentForm()
    if form.validate_on_submit():
        comment = Comment(
            content=form.content.data,
            bill_id=bill.id,
            author_id=current_user.id if current_user.is_authenticated else None,
            guest_name=form.guest_name.data if not current_user.is_authenticated else None
        )
        
        db.session.add(comment)
        db.session.commit()
        
        flash("Comment added successfully!", "success")
        return redirect(url_for("bills.view_bill", bill_slug=bill_slug))
    
    return render_template("bills/add_comment.html", bill=bill, form=form)


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/reply", methods=["GET", "POST"])
def reply_to_comment(bill_slug, comment_id):
    """Reply to a comment on a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    parent_comment = Comment.query.get_or_404(comment_id)
    if parent_comment.bill_id != bill.id:
        abort(404)
    
    form = BillCommentForm()
    if form.validate_on_submit():
        reply = Comment(
            content=form.content.data,
            bill_id=bill.id,
            parent_id=comment_id,
            author_id=current_user.id if current_user.is_authenticated else None,
            guest_name=form.guest_name.data if not current_user.is_authenticated else None
        )
        
        db.session.add(reply)
        db.session.commit()
        
        flash("Reply added successfully!", "success")
        return redirect(url_for("bills.view_bill", bill_slug=bill_slug))
    
    return render_template("bills/add_reply.html", bill=bill, parent_comment=parent_comment, form=form)


@bills_bp.route("/bills/<bill_slug>/report")
def report_bill(bill_slug):
    """Report a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    # TODO: Implement bill reporting functionality
    flash("Bill reporting functionality coming soon!", "info")
    return redirect(url_for("bills.view_bill", bill_slug=bill_slug))


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/report")
def report_comment(bill_slug, comment_id):
    """Report a comment on a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    comment = Comment.query.get_or_404(comment_id)
    if comment.bill_id != bill.id:
        abort(404)
    
    # TODO: Implement comment reporting functionality
    flash("Comment reporting functionality coming soon!", "info")
    return redirect(url_for("bills.view_bill", bill_slug=bill_slug))


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_comment(bill_slug, comment_id):
    """Edit a comment on a bill (reused from blog.py)"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    comment = Comment.query.get_or_404(comment_id)
    if comment.bill_id != bill.id:
        abort(404)
    
    # Check if user can edit this comment
    if comment.author_id != current_user.id and not current_user.is_admin():
        abort(403)
    
    from app.forms import CommentEditForm
    form = CommentEditForm(comment_id=comment.id)
    
    if form.validate_on_submit():
        comment.content = form.content.data
        comment.mark_edited()
        db.session.commit()
        return redirect(
            url_for("bills.view_bill", bill_slug=bill_slug) + f"#c{comment.id}"
        )
    
    form.content.data = comment.content
    return render_template("bills/edit_comment.html", form=form, comment=comment, bill=bill)


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/remove", methods=["POST"])
def remove_comment(bill_slug, comment_id):
    """Remove a comment on a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    comment = Comment.query.get_or_404(comment_id)
    if comment.bill_id != bill.id:
        abort(404)
    
    # TODO: Implement comment removal functionality
    flash("Comment removal functionality coming soon!", "info")
    return redirect(url_for("bills.view_bill", bill_slug=bill_slug))


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/thread", methods=["GET", "POST"])
def comment_thread(bill_slug, comment_id):
    """View a comment thread (reused from blog.py)"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    root = Comment.query.get_or_404(comment_id)
    if root.bill_id != bill.id:
        abort(404)
    
    form = BillCommentForm()
    if form.validate_on_submit():
        if not current_user.is_authenticated:
            abort(403)
        comment = Comment(
            content=form.content.data,
            author_id=current_user.id,
            bill_id=root.bill_id,
            parent_id=form.parent_id.data or None,
        )
        db.session.add(comment)
        db.session.commit()
        
        flash("Reply added successfully!", "success")
        return redirect(url_for("bills.comment_thread", bill_slug=bill_slug, comment_id=comment_id))
    
    # Populate the thread with nested replies
    populate_replies(root)
    
    return render_template("bills/comment_thread.html", root=root, form=form, bill=bill)


@bills_bp.route("/api/bills/hot")
def api_hot_bills():
    """API endpoint to get hot bills for the dropdown"""
    from app.tasks import get_bills_for_display
    bills = get_bills_for_display(limit=10)
    return {
        'bills': [
            {
                'number': bill.bill_number,
                'title': bill.display_title,
                'slug': bill.slug,
                'chamber': bill.chamber,
                'created_at': bill.created_at.isoformat() if bill.created_at else None
            }
            for bill in bills
        ]
    }


@bills_bp.route("/bills")
def list_bills():
    """List all bills with pagination"""
    page = request.args.get("page", 1, type=int)
    chamber_filter = request.args.get("chamber", "")
    search_query = request.args.get("search", "").strip()
    
    # Build the base query
    query = Bill.query
    
    # Apply chamber filter
    if chamber_filter and chamber_filter in ["House", "Senate", "Joint"]:
        query = query.filter(Bill.chamber == chamber_filter)
    
    # Apply search filter
    if search_query:
        query = query.filter(
            db.or_(
                Bill.title.ilike(f"%{search_query}%"),
                Bill.bill_number.ilike(f"%{search_query}%")
            )
        )
    
    # Order by two-tier ranking:
    # 1. Bills with recent comments (sorted by most recent comment timestamp)
    # 2. Bills without comments (sorted by creation date, newest first)
    from sqlalchemy import func, case
    query = (
        query.outerjoin(Comment, Bill.id == Comment.bill_id)
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
    )
    
    # Paginate results
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    bills = pagination.items
    
    # Get comment counts for each bill
    bill_data = []
    for bill in bills:
        comment_count = Comment.query.filter_by(bill_id=bill.id).count()
        latest_comment = (
            Comment.query.filter_by(bill_id=bill.id)
            .order_by(Comment.timestamp.desc())
            .first()
        )
        bill_data.append({
            "bill": bill,
            "comments": comment_count,
            "latest_comment": latest_comment.timestamp if latest_comment else None
        })
    
    # Get recent comments for sidebar
    recent_comments = Comment.query.order_by(Comment.timestamp.desc()).limit(5).all()
    
    # Get trending tags for sidebar
    from app.models import Tag, Post
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
    
    return render_template("bills/list.html",
                         bills=bill_data,
                         pagination=pagination,
                         chamber_filter=chamber_filter,
                         search_query=search_query,
                         recent_comments=recent_comments,
                         trending_tags=trending_tags)


@bills_bp.route("/bills/manual-scrape", methods=["POST"])
@login_required
def manual_scrape():
    """Manually trigger bill scraping (admin only)"""
    if current_user.role != 'admin':
        flash("Access denied. Admin privileges required.", "error")
        return redirect(url_for('blog.index'))
    
    try:
        from app.tasks import scrape_ma_bills
        
        # Run the scraping function
        scrape_ma_bills()
        
        # Get updated count
        bill_count = Bill.query.count()
        
        flash(f"Bill scraping completed successfully! Found {bill_count} bills total.", "success")
        
    except Exception as e:
        current_app.logger.error(f"Manual bill scraping failed: {e}")
        flash(f"Bill scraping failed: {str(e)}", "error")
    
    return redirect(url_for('blog.index')) 