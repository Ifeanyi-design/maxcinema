from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from . import admin_bp
from .forms import StorageServerForm
from ..models import AllVideo, StorageServer, db, Trailer, MovieRequest, User
from .helpers import admin_required


@admin_bp.route("/storage-servers")
@login_required
@admin_required
def view_storage():
    server = True
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()
    servers = StorageServer.query.order_by(StorageServer.created_at.desc()).all()
    return render_template("admin/view_storage.html", server=server, servers=servers, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route("/storage-servers/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_storage_server():
    form = StorageServerForm()
    if form.validate_on_submit():
        new_server = StorageServer()

        form.populate_obj(new_server)

        new_server.used_storage_gb = 0.0

        try:
            db.session.add(new_server)
            db.session.commit()
            flash(f"Storage Server '{new_server.name}' added successfully!", "success")
            return redirect(url_for('admin.view_storage'))

        except Exception as e:
            db.session.rollback()
            if "UNIQUE constraint" in str(e) or "unique constraint" in str(e).lower():
                flash("Error: A server with that name already exists.", "error")
            else:
                flash(f"Database error: {str(e)}", "error")

    return render_template("admin/add_storage_server.html", form=form, title="Add New Server")


@admin_bp.route("/storage-servers/edit/<int:server_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_storage_server(server_id):
    edit = True
    server = StorageServer.query.get_or_404(server_id)

    form = StorageServerForm(obj=server)

    if form.validate_on_submit():
        form.populate_obj(server)

        try:
            db.session.commit()
            flash(f"Server '{server.name}' updated successfully.", "success")
            return redirect(url_for('admin.view_storage'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating server: {str(e)}", "error")

    return render_template("admin/add_storage_server.html", edit=edit, form=form, title=f"Edit {server.name}")


@admin_bp.route("/storage-servers/delete/<int:server_id>", methods=["POST"])
@login_required
@admin_required
def delete_storage_server(server_id):
    server = StorageServer.query.get_or_404(server_id)

    try:
        db.session.delete(server)
        db.session.commit()
        flash(f"Server '{server.name}' deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error deleting server.", "error")

    return redirect(url_for("admin.view_storage"))
