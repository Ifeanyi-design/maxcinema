import re
import requests as http_requests
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import admin_bp
from .helpers import admin_required
from ..extensions import db
from ..models import SocialVideo, AllVideo


def _parse_social_url(url):
    """Extract platform and video ID from a YouTube or TikTok URL."""
    url = url.strip()

    # YouTube patterns (covers shorts, watch, embed, youtu.be, m., music., query params)
    yt_match = re.search(
        r'(?:www\.|m\.|music\.)?(?:youtube\.com/(?:shorts/|watch\?v=|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})',
        url
    )
    if yt_match:
        return 'youtube', yt_match.group(1)

    # TikTok patterns
    tt_match = re.search(
        r'tiktok\.com/@[^/]+/video/(\d+)',
        url
    )
    if tt_match:
        return 'tiktok', tt_match.group(1)

    return None, None


def _fetch_youtube_oembed(video_id):
    """Fetch YouTube metadata via oEmbed (no API key needed)."""
    try:
        resp = http_requests.get(
            f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json',
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            thumbnail = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            return {
                'title': data.get('title', ''),
                'description': data.get('author_name', ''),
                'thumbnail_url': thumbnail,
            }
    except Exception:
        pass
    return None


def _fetch_tiktok_oembed(video_id):
    """Fetch TikTok thumbnail via oEmbed."""
    try:
        resp = http_requests.get(
            f'https://www.tiktok.com/oembed?url=https://www.tiktok.com/video/{video_id}',
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                'title': data.get('title', ''),
                'description': data.get('author_name', ''),
                'thumbnail_url': data.get('thumbnail_url', ''),
            }
    except Exception:
        pass
    return None


def _auto_match_all_video(title):
    """Try to find an AllVideo matching the social video title."""
    if not title:
        return None
    # Exact match first
    match = AllVideo.query.filter(db.func.lower(AllVideo.name) == title.lower().strip()).first()
    if match:
        return match
    # Partial match — title contains the movie name or vice versa
    all_videos = AllVideo.query.filter(AllVideo.active == True).all()
    title_lower = title.lower().strip()
    # Remove common filler words for matching
    stop_words = {'the', 'a', 'an', 'edit', 'fan', 'official', 'trailer', 'clip', 'scene', 'compilation', 'best', 'funny', 'movie', 'video', 'tiktok', 'youtube', 'shorts'}
    title_words = set(title_lower.split()) - stop_words
    best_match = None
    best_score = 0
    for av in all_videos:
        av_words = set(av.name.lower().split()) - stop_words
        overlap = len(title_words & av_words)
        if overlap > best_score:
            best_score = overlap
            best_match = av
    if best_score >= 1:
        return best_match
    return None


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
    all_videos = AllVideo.query.order_by(AllVideo.name.asc()).all()
    prefilled = {}

    if request.method == 'POST':
        video_url = request.form.get('video_url', '').strip()
        platform, platform_id = _parse_social_url(video_url)

        if not platform:
            flash('Could not detect platform from URL. Use a YouTube or TikTok video URL.', 'danger')
            return render_template('admin/add_social_video.html', all_videos=all_videos, prefilled={'video_url': video_url})

        # Check for duplicate
        existing = SocialVideo.query.filter_by(platform=platform, platform_id=platform_id).first()
        if existing:
            flash(f'This video already exists (ID: {existing.id}).', 'warning')
            return redirect(url_for('admin.view_social_videos'))

        # Fetch metadata
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        thumbnail_url = request.form.get('thumbnail_url', '').strip()
        tags = request.form.get('tags', '').strip()
        all_video_id = request.form.get('all_video_id', '')
        featured = 'featured' in request.form
        active = 'active' in request.form
        sort_order = request.form.get('sort_order', 0, type=int)

        if platform == 'youtube':
            oembed = _fetch_youtube_oembed(platform_id)
            if oembed:
                if not title:
                    title = oembed['title']
                if not description:
                    description = oembed['description']
                if not thumbnail_url:
                    thumbnail_url = oembed['thumbnail_url']
        elif platform == 'tiktok':
            oembed = _fetch_tiktok_oembed(platform_id)
            if oembed:
                if not thumbnail_url:
                    thumbnail_url = oembed.get('thumbnail_url', '')
                if not title and oembed.get('title'):
                    title = oembed['title']

        if not title:
            title = f'{platform.title()} Video {platform_id}'

        # Auto-match associated content if not manually selected
        all_video_id_val = request.form.get('all_video_id', '')
        matched_video = None
        if not all_video_id_val:
            matched_video = _auto_match_all_video(title)
            if matched_video:
                all_video_id_val = str(matched_video.id)

        sv = SocialVideo(
            platform=platform,
            video_url=video_url,
            platform_id=platform_id,
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            tags=tags,
            all_video_id=int(all_video_id_val) if all_video_id_val else None,
            featured=featured,
            active=active,
            sort_order=sort_order,
        )
        db.session.add(sv)
        db.session.commit()

        match_msg = f' (auto-matched to "{matched_video.name}")' if matched_video else ''
        flash(f'Added "{sv.title}" ({platform}){match_msg}.', 'success')
        return redirect(url_for('admin.view_social_videos'))

    return render_template('admin/add_social_video.html', all_videos=all_videos, prefilled={})
