from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required
from werkzeug.security import generate_password_hash

from . import admin_bp
from .forms import UserForm
from ..models import AllVideo, User, db, Trailer, MovieRequest
from .helpers import admin_required


@admin_bp.route("/users")
@login_required
@admin_required
def view_users():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    users = User.query.all()
    len_users = len(users)
    user = True
    return render_template("admin/users.html", user=user, len_users=len_users, users=users, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route("/add-user", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "danger")
            return render_template("admin/user_form.html", form=form)
        password = generate_password_hash(form.password_hash.data)
        user = User(
            username=form.username.data,
            email=form.email.data,
            is_admin=form.is_admin.data,
            password_hash=password
        )
        db.session.add(user)
        db.session.commit()
        flash("User added successfully.", "success")
        return redirect(url_for("admin.view_users"))
    return render_template("admin/user_form.html", form=form)


@admin_bp.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    if form.validate_on_submit():
        if user.email != form.email.data and User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "danger")
            return render_template("admin/user_form.html", form=form, user=user)
        form.populate_obj(user)
        if form.password_hash.data:
            user.password_hash = generate_password_hash(form.password_hash.data)
        db.session.commit()
        flash("User updated successfully.", "success")
        return redirect(url_for("admin.view_users"))
    return render_template("admin/user_form.html", form=form, user=user)


@admin_bp.route("/delete-user/<int:user_id>", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("admin.view_users"))
