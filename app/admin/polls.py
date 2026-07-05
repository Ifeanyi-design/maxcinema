from datetime import datetime

from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from . import admin_bp
from ..models import AllVideo, db, Trailer, MovieRequest, User, WeeklyPoll, WeeklyPollOption, WeeklyPollVote
from .helpers import admin_required


@admin_bp.route('/admin/polls', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_polls():
    total_movies = AllVideo.query.filter_by(type='movie').count()
    total_series = AllVideo.query.filter_by(type='series').count()
    total_trailers = Trailer.query.count()
    total_users = User.query.count()
    total_views = db.session.query(db.func.sum(AllVideo.views)).scalar() or 0
    total_requests = MovieRequest.query.filter_by(status='Pending').count()

    if request.method == 'POST':
        question = (request.form.get('question') or '').strip()
        options_text = (request.form.get('options') or '').strip()
        is_active = request.form.get('is_active') == 'on'

        if not question or not options_text:
            flash('Question and options are required.', 'error')
            return redirect(url_for('admin.manage_polls'))

        options_list = [o.strip() for o in options_text.split('\n') if o.strip()]
        if len(options_list) < 2:
            flash('At least 2 options are required.', 'error')
            return redirect(url_for('admin.manage_polls'))
        if len(options_list) > 8:
            flash('Maximum 8 options allowed.', 'error')
            return redirect(url_for('admin.manage_polls'))

        if is_active:
            WeeklyPoll.query.update({'is_active': False})

        poll = WeeklyPoll(
            question=question,
            is_active=is_active,
            starts_at=datetime.utcnow()
        )
        db.session.add(poll)
        db.session.commit()

        for opt_text in options_list:
            option = WeeklyPollOption(poll_id=poll.id, option_text=opt_text, votes=0)
            db.session.add(option)
        db.session.commit()

        flash('Poll created successfully.', 'success')
        return redirect(url_for('admin.manage_polls'))

    polls = WeeklyPoll.query.order_by(WeeklyPoll.date_added.desc()).all()
    return render_template('admin/polls.html', polls=polls, total_movies=total_movies, total_series=total_series, total_trailers=total_trailers, total_users=total_users, total_views=total_views, total_requests=total_requests)


@admin_bp.route('/admin/polls/activate/<int:poll_id>')
@login_required
@admin_required
def activate_poll(poll_id):
    poll = WeeklyPoll.query.get_or_404(poll_id)
    WeeklyPoll.query.update({'is_active': False})
    poll.is_active = True
    db.session.commit()
    flash('Poll activated.', 'success')
    return redirect(url_for('admin.manage_polls'))


@admin_bp.route('/admin/polls/delete/<int:poll_id>')
@login_required
@admin_required
def delete_poll(poll_id):
    poll = WeeklyPoll.query.get_or_404(poll_id)
    db.session.delete(poll)
    db.session.commit()
    flash('Poll deleted.', 'success')
    return redirect(url_for('admin.manage_polls'))
