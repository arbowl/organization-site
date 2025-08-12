# app/analytics.py

from os import getenv
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import current_user
from sqlalchemy import func, desc, asc

from app import db
from app.models import Visit

HOST_DOMAIN = getenv("HOST_DOMAIN", "localhost")
analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
def dashboard():
    if not current_user.is_authenticated or not current_user.is_admin():
        return redirect(url_for("blog.index"))

    metric = request.args.get("metric", "referrers")
    sort_by = request.args.get("sort", "count")
    order = request.args.get("order", "desc")

    sort_column = "label" if sort_by == "label" else "count"
    direction = asc if order == "asc" else desc

    if metric == "ips":
        q = db.session.query(
            Visit.ip_address.label("label"), func.count().label("count")
        ).group_by(Visit.ip_address)
    else:
        metric = "referrers"
        # Filter out internal referrers
        all_visits: list[Visit] = (
            db.session.query(Visit.referrer).filter(Visit.referrer != None).all()
        )
        external_referrers = [
            r.referrer
            for r in all_visits
            if not urlparse(r.referrer).netloc.endswith(HOST_DOMAIN)
        ]

        q = (
            db.session.query(Visit.referrer.label("label"), func.count().label("count"))
            .filter(Visit.referrer.in_(external_referrers))
            .group_by(Visit.referrer)
        )

    q = q.order_by(direction(sort_column))
    rows = q.all()

    labels = [r.label or "(none)" for r in rows]
    counts = [r.count for r in rows]

    return render_template(
        "analytics/dashboard.html",
        metric=metric,
        rows=rows,
        labels=labels,
        counts=counts,
        sort_by=sort_by,
        order=order,
    )
