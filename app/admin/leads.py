import csv
import io

from flask import render_template, redirect, url_for, request, flash, Response
from flask_login import login_required

from . import admin_bp
from ..models import AllVideo, db, Trailer, MovieRequest, User, CourseLead
from .helpers import admin_required


@admin_bp.route('/leads')
@login_required
@admin_required
def leads_dashboard():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    course_filter = request.args.get('course', '').strip()
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = CourseLead.query

    if course_filter:
        query = query.filter(CourseLead.course_interest == course_filter)
    if search:
        query = query.filter(
            (CourseLead.name.ilike(f'%{search}%')) |
            (CourseLead.email.ilike(f'%{search}%'))
        )

    total_leads = query.count()
    leads_page = query.order_by(CourseLead.date_added.desc()).paginate(page=page, per_page=per_page, error_out=False)

    courses = db.session.query(CourseLead.course_interest).distinct().all()
    courses = [c[0] for c in courses]

    return render_template(
        'admin/leads.html',
        leads_page=leads_page,
        total_leads=total_leads,
        courses=courses,
        course_filter=course_filter,
        search_query=search,
        total_movies=total_movies,
        total_series=total_series,
        total_trailers=total_trailers,
        total_users=total_users,
        total_views=total_views,
        total_requests=total_requests
    )


@admin_bp.route('/leads/export')
@login_required
@admin_required
def export_leads():
    course_filter = request.args.get('course', '').strip()
    search = request.args.get('search', '').strip()

    query = CourseLead.query

    if course_filter:
        query = query.filter(CourseLead.course_interest == course_filter)
    if search:
        query = query.filter(
            (CourseLead.name.ilike(f'%{search}%')) |
            (CourseLead.email.ilike(f'%{search}%'))
        )

    leads = query.order_by(CourseLead.date_added.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Email', 'Phone', 'Course Interest', 'Date Added'])
    for lead in leads:
        writer.writerow([
            lead.name,
            lead.email,
            lead.phone or '',
            lead.course_interest,
            lead.date_added.strftime('%Y-%m-%d %H:%M') if lead.date_added else ''
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=leads_export.csv'}
    )


@admin_bp.route('/leads/delete/<int:lead_id>', methods=['POST'])
@login_required
@admin_required
def delete_lead(lead_id):
    lead = CourseLead.query.get_or_404(lead_id)
    db.session.delete(lead)
    db.session.commit()
    flash('Lead deleted successfully.', 'success')
    return redirect(url_for('admin.leads_dashboard'))
