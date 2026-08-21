from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import admin_bp
from .helpers import admin_required
from ..extensions import db
from ..models import SocialVideo, AllVideo


@admin_bp.route('/social-videos')
@login_required
@admin_required
def view_social_videos():
    platform = request.args.get('platform', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)
    per_page = 30

    query = SocialVideo.query

    if platform in ('youtube', 'tiktok'):
        query = query.filter_by(platform=platform)
    if status == 'active':
        query = query.filter_by(active=True)
    elif status == 'inactive':
        query = query.filter_by(active=False)
    elif status == 'featured':
        query = query.filter_by(featured=True)

    query = query.order_by(SocialVideo.sort_order.asc(), SocialVideo.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    total = SocialVideo.query.count()
    total_active = SocialVideo.query.filter_by(active=True).count()
    total_featured = SocialVideo.query.filter_by(featured=True).count()
    total_youtube = SocialVideo.query.filter_by(platform='youtube').count()
    total_tiktok = SocialVideo.query.filter_by(platform='tiktok').count()

    all_videos = AllVideo.query.order_by(AllVideo.name.asc()).all()

    return render_template(
        'admin/social_videos.html',
        videos=pagination.items,
        pagination=pagination,
        all_videos=all_videos,
        total=total,
        total_active=total_active,
        total_featured=total_featured,
        total_youtube=total_youtube,
        total_tiktok=total_tiktok,
        current_platform=platform,
        current_status=status,
    )


@admin_bp.route('/social-videos/save', methods=['POST'])
@login_required
@admin_required
def save_social_videos():
    ids = request.form.getlist('video_ids[]')
    updated = 0

    for vid_id in ids:
        sv = SocialVideo.query.get(int(vid_id))
        if not sv:
            continue

        sv.title = request.form.get(f'title_{vid_id}', sv.title).strip()
        sv.sort_order = request.form.get(f'sort_order_{vid_id}', sv.sort_order, type=int)

        all_video_id = request.form.get(f'all_video_id_{vid_id}', '')
        sv.all_video_id = int(all_video_id) if all_video_id else None

        sv.featured = f'featured_{vid_id}' in request.form
        sv.active = f'active_{vid_id}' in request.form

        updated += 1

    db.session.commit()
    flash(f'Updated {updated} social video(s).', 'success')
    return redirect(url_for('admin.view_social_videos'))


@admin_bp.route('/social-videos/delete', methods=['POST'])
@login_required
@admin_required
def delete_social_videos():
    ids = request.form.getlist('video_ids[]')
    deleted = 0
    for vid_id in ids:
        sv = SocialVideo.query.get(int(vid_id))
        if sv:
            db.session.delete(sv)
            deleted += 1
    db.session.commit()
    flash(f'Deleted {deleted} social video(s).', 'success')
    return redirect(url_for('admin.view_social_videos'))


@admin_bp.route('/social-videos/bulk-featured', methods=['POST'])
@login_required
@admin_required
def bulk_featured_social_videos():
    ids = request.form.getlist('video_ids[]')
    value = request.form.get('value', 'true') == 'true'
    count = 0
    for vid_id in ids:
        sv = SocialVideo.query.get(int(vid_id))
        if sv:
            sv.featured = value
            count += 1
    db.session.commit()
    flash(f'Set featured={value} for {count} video(s).', 'success')
    return redirect(url_for('admin.view_social_videos'))


@admin_bp.route('/social-videos/bulk-active', methods=['POST'])
@login_required
@admin_required
def bulk_active_social_videos():
    ids = request.form.getlist('video_ids[]')
    value = request.form.get('value', 'true') == 'true'
    count = 0
    for vid_id in ids:
        sv = SocialVideo.query.get(int(vid_id))
        if sv:
            sv.active = value
            count += 1
    db.session.commit()
    flash(f'Set active={value} for {count} video(s).', 'success')
    return redirect(url_for('admin.view_social_videos'))


@admin_bp.route('/social-videos/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_social_video():
    if request.method == 'POST':
        flash('Add form not yet implemented.', 'warning')
        return redirect(url_for('admin.view_social_videos'))
    return redirect(url_for('admin.view_social_videos'))
