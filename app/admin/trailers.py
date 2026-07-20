from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from . import admin_bp
from .forms import TrailerForm
from ..models import AllVideo, Trailer, db, MovieRequest, User
from ..indexnow import (
    submit_for_trailer, submit_indexnow_urls, build_trailer_url,
)
from .helpers import admin_required


@admin_bp.route("/trailers")
@admin_bp.route("/trailers/<int:page>")
@login_required
@admin_required
def view_trailers(page=1):
    per_page = 30
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    trailers = Trailer.query.order_by(Trailer.date_added.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template("admin/trailers.html", trailers=trailers, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route("/delete-trailer/<int:trailer_id>", methods=["GET", "POST"])
@login_required
@admin_required
def delete_trailer(trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    deleted_urls = [
        build_trailer_url(trailer),
        url_for("main.trailer", _external=True),
        url_for("main.index", _external=True),
        url_for("main.sitemap", _external=True),
    ]
    db.session.delete(trailer)
    db.session.commit()
    submit_indexnow_urls(deleted_urls)
    return redirect(url_for("admin.view_trailers"))


@admin_bp.route("/edit-trailer/<prev>/<slug>/<int:trailer_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_trailer(prev, slug, trailer_id):
    trailer = Trailer.query.get_or_404(trailer_id)
    form = TrailerForm(obj=trailer)
    if form.validate_on_submit():
        form.populate_obj(trailer)
        db.session.commit()
        submit_for_trailer(trailer)
        flash(f"Trailer {trailer.name} updated.", "success")
        return redirect(url_for("admin.view_trailers"))
    return render_template("admin/trailer_form.html", form=form)


@admin_bp.route("/add-trailer/<prev>", methods=["GET", "POST"])
@login_required
@admin_required
def add_trailer(prev):
    new_trailer = Trailer()
    form = TrailerForm()
    if form.validate_on_submit():
        form.populate_obj(new_trailer)
        db.session.add(new_trailer)
        db.session.commit()
        submit_for_trailer(new_trailer)
        return redirect(url_for("admin.view_trailers"))
    return render_template("admin/trailer_form.html", form=form)
