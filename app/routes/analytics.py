# app/analytics.py

from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import current_user
from sqlalchemy import func, desc, asc
from app import db
from app.models import Visit

analytics_bp = Blueprint('analytics', __name__, url_prefix='/analytics')

@analytics_bp.route('/')
def dashboard():
    if not current_user.is_authenticated or not current_user.is_admin():
        return redirect(url_for("blog.index"))
    metric = request.args.get('metric', 'referrers')
    sort_by = request.args.get('sort',   'count')
    order = request.args.get('order',  'desc')
    if metric == 'ips':
        label_col = Visit.ip_address
        q = db.session.query(
            Visit.ip_address.label('label'),
            func.count().label('count')
        ).group_by(Visit.ip_address)
    else:
        metric = 'referrers'
        label_col = Visit.referrer
        q = db.session.query(
            Visit.referrer.label('label'),
            func.count().label('count')
        ).filter(Visit.referrer != None).group_by(Visit.referrer)
    sort_column = 'label' if sort_by == 'label' else 'count'
    direction = asc if order=='asc' else desc
    q = q.order_by(direction(sort_column))
    rows = q.all()
    labels = [r.label or '(none)' for r in rows]
    counts = [r.count for r in rows]
    return render_template(
      'analytics/dashboard.html',
      metric = metric,
      rows = rows,
      labels = labels,
      counts = counts,
      sort_by = sort_by,
      order = order
    )
