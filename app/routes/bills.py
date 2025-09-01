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


@bills_bp.route("/bills/<bill_slug>")
def view_bill(bill_slug):
    """Display a specific bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    # Get comments for this bill
    comments = Comment.query.filter_by(bill_id=bill.id, parent_id=None).order_by(Comment.timestamp.desc()).all()
    
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
    
    # Create form for inline commenting
    from app.forms import BillCommentForm
    form = BillCommentForm()
    
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


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/edit")
def edit_comment(bill_slug, comment_id):
    """Edit a comment on a bill"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    comment = Comment.query.get_or_404(comment_id)
    if comment.bill_id != bill.id:
        abort(404)
    
    # TODO: Implement comment editing functionality
    flash("Comment editing functionality coming soon!", "info")
    return redirect(url_for("bills.view_bill", bill_slug=bill_slug))


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


@bills_bp.route("/bills/<bill_slug>/comment/<int:comment_id>/thread")
def comment_thread(bill_slug, comment_id):
    """View a comment thread"""
    bill = get_bill_by_slug(bill_slug)
    if not bill:
        abort(404)
    
    comment = Comment.query.get_or_404(comment_id)
    if comment.bill_id != bill.id:
        abort(404)
    
    # TODO: Implement comment thread functionality
    flash("Comment thread functionality coming soon!", "info")
    return redirect(url_for("bills.view_bill", bill_slug=bill_slug))


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