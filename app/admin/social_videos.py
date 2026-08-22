import os
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


def _fetch_tiktok_oembed(video_url):
    """Fetch TikTok title + thumbnail via oEmbed (no API key needed)."""
    try:
        resp = http_requests.get(
            'https://www.tiktok.com/oembed',
            params={'url': video_url},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                'title': data.get('title', ''),
                'description': data.get('title', ''),
                'thumbnail_url': data.get('thumbnail_url', ''),
            }
    except Exception:
        pass
    return None


def _fetch_youtube_video_details(video_ids, api_key):
    """Fetch YouTube video details (title, description, tags, thumbnail) via Data API v3."""
    try:
        resp = http_requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'part': 'snippet',
                'id': ','.join(video_ids),
                'key': api_key,
            },
            timeout=15
        )
        data = resp.json()
        results = {}
        for item in data.get('items', []):
            vid_id = item['id']
            snippet = item.get('snippet', {})
            tags = snippet.get('tags', [])
            results[vid_id] = {
                'title': snippet.get('title', ''),
                'description': snippet.get('description', ''),
                'tags': ', '.join(tags) if tags else '',
                'thumbnail_url': f'https://img.youtube.com/vi/{vid_id}/hqdefault.jpg',
            }
        return results
    except Exception:
        return {}


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

        # Many-to-many: get all selected video IDs
        all_video_ids = request.form.getlist(f'all_video_ids_{vid_id}[]')
        sv.all_videos = AllVideo.query.filter(AllVideo.id.in_([int(x) for x in all_video_ids if x])).all() if all_video_ids else []

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


@admin_bp.route('/social-videos/fetch-meta', methods=['POST'])
@login_required
@admin_required
def social_fetch_meta():
    payload = request.get_json(silent=True) or {}
    video_url = (payload.get('video_url') or '').strip()
    platform, platform_id = _parse_social_url(video_url)
    if not platform:
        return jsonify({'ok': False, 'error': 'Could not detect platform from URL.'}), 400

    title = description = thumbnail_url = tags = ''
    if platform == 'youtube':
        oe = _fetch_youtube_oembed(platform_id)
        if oe:
            title = oe.get('title', '')
            description = oe.get('description', '')
            thumbnail_url = oe.get('thumbnail_url', '')
        api_key = os.environ.get('YOUTUBE_API_KEY', '')
        if api_key:
            details = _fetch_youtube_video_details([platform_id], api_key)
            if platform_id in details:
                tags = details[platform_id].get('tags', '')
                if not description:
                    description = details.get('description', '')
    else:
        oe = _fetch_tiktok_oembed(video_url)
        if oe:
            title = oe.get('title', '')
            description = oe.get('description', '')
            thumbnail_url = oe.get('thumbnail_url', '')

    return jsonify({
        'ok': True,
        'platform': platform,
        'title': title,
        'description': description,
        'thumbnail_url': thumbnail_url,
        'tags': tags,
    })


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
            # Fetch tags via Data API if available
            api_key = os.environ.get('YOUTUBE_API_KEY', '')
            if api_key:
                details = _fetch_youtube_video_details([platform_id], api_key)
                if platform_id in details:
                    if not tags:
                        tags = details[platform_id].get('tags', '')
                    if not description:
                        description = details[platform_id].get('description', '')
        elif platform == 'tiktok':
            oembed = _fetch_tiktok_oembed(video_url)
            if oembed:
                if not thumbnail_url:
                    thumbnail_url = oembed.get('thumbnail_url', '')
                if not title and oembed.get('title'):
                    title = oembed['title']

        if not title:
            title = f'{platform.title()} Video {platform_id}'

        # Auto-match associated content if not manually selected
        all_video_ids = request.form.getlist('all_video_ids[]')
        matched_video = None
        if not all_video_ids:
            matched_video = _auto_match_all_video(title)
            if matched_video:
                all_video_ids = [str(matched_video.id)]

        sv = SocialVideo(
            platform=platform,
            video_url=video_url,
            platform_id=platform_id,
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            tags=tags,
            featured=featured,
            active=active,
            sort_order=sort_order,
        )
        if all_video_ids:
            sv.all_videos = AllVideo.query.filter(AllVideo.id.in_([int(x) for x in all_video_ids if x])).all()
        db.session.add(sv)
        db.session.commit()

        match_names = ', '.join([av.name for av in sv.all_videos])
        match_msg = f' (linked to: {match_names})' if match_names else ''
        flash(f'Added "{sv.title}" ({platform}){match_msg}.', 'success')
        return redirect(url_for('admin.view_social_videos'))

    return render_template('admin/add_social_video.html', all_videos=all_videos, prefilled={})


@admin_bp.route('/social-videos/sync-youtube', methods=['POST'])
@login_required
@admin_required
def sync_youtube():
    api_key = os.environ.get('YOUTUBE_API_KEY', '')
    channel_id = os.environ.get('YOUTUBE_CHANNEL_ID', '')

    if not api_key or not channel_id:
        flash('YouTube API key or Channel ID not configured. Set YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID in environment.', 'danger')
        return redirect(url_for('admin.view_social_videos'))

    # Step 1: Get the channel's uploads playlist ID
    try:
        channel_resp = http_requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'contentDetails',
                'id': channel_id,
                'key': api_key,
            },
            timeout=15
        )
        channel_data = channel_resp.json()
        if 'items' not in channel_data or not channel_data['items']:
            flash(f'Channel not found. Check YOUTUBE_CHANNEL_ID. Response: {channel_data.get("error", {}).get("message", "unknown")}', 'danger')
            return redirect(url_for('admin.view_social_videos'))

        uploads_playlist_id = channel_data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    except Exception as e:
        flash(f'Error fetching channel: {str(e)}', 'danger')
        return redirect(url_for('admin.view_social_videos'))

    # Step 2: Fetch ALL videos from uploads playlist (paginated)
    try:
        all_items = []
        next_page_token = None
        while True:
            params = {
                'part': 'snippet,contentDetails',
                'playlistId': uploads_playlist_id,
                'maxResults': 50,
                'key': api_key,
            }
            if next_page_token:
                params['pageToken'] = next_page_token

            playlist_resp = http_requests.get(
                'https://www.googleapis.com/youtube/v3/playlistItems',
                params=params,
                timeout=15
            )
            playlist_data = playlist_resp.json()
            if 'items' not in playlist_data:
                flash(f'Error fetching playlist: {playlist_data.get("error", {}).get("message", "unknown")}', 'danger')
                return redirect(url_for('admin.view_social_videos'))

            all_items.extend(playlist_data['items'])
            next_page_token = playlist_data.get('nextPageToken')
            if not next_page_token:
                break

        items = all_items
    except Exception as e:
        flash(f'Error fetching videos: {str(e)}', 'danger')
        return redirect(url_for('admin.view_social_videos'))

    # Step 3: Fetch full details (title, tags) via videos.list API
    video_ids = [item['contentDetails']['videoId'] for item in items]
    video_details = _fetch_youtube_video_details(video_ids, api_key)

    # Step 4: Insert new videos, skip existing
    synced = 0
    skipped = 0
    for item in items:
        video_id = item['contentDetails']['videoId']
        snippet = item['snippet']

        # Skip if already exists
        existing = SocialVideo.query.filter_by(platform='youtube', platform_id=video_id).first()
        if existing:
            skipped += 1
            continue

        # Use full details if available, fall back to playlist snippet
        details = video_details.get(video_id, {})
        title = details.get('title') or snippet.get('title', '')
        description = details.get('description') or snippet.get('description', '')
        tags = details.get('tags', '')
        thumbnail_url = details.get('thumbnail_url') or f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
        published_at = snippet.get('publishedAt', '')

        # Parse published_at
        pub_date = None
        if published_at:
            try:
                from datetime import datetime
                pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00')).replace(tzinfo=None)
            except Exception:
                pass

        sv = SocialVideo(
            platform='youtube',
            video_url=f'https://youtube.com/shorts/{video_id}' if len(video_id) == 11 else f'https://youtube.com/watch?v={video_id}',
            platform_id=video_id,
            title=title,
            description=description,
            thumbnail_url=thumbnail_url,
            tags=tags,
            published_at=pub_date,
            active=True,
        )

        # Auto-match associated content
        matched = _auto_match_all_video(title)
        if matched:
            sv.all_videos = [matched]

        db.session.add(sv)
        synced += 1

    db.session.commit()

    flash(f'YouTube sync complete: {synced} new video(s) imported, {skipped} already existed.', 'success')
    return redirect(url_for('admin.view_social_videos'))


@admin_bp.route('/social-videos/edit/<int:sv_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_social_video(sv_id):
    sv = SocialVideo.query.get_or_404(sv_id)
    all_videos = AllVideo.query.order_by(AllVideo.name.asc()).all()

    if request.method == 'POST':
        sv.video_url = request.form.get('video_url', sv.video_url).strip()
        sv.title = request.form.get('title', sv.title).strip()
        sv.description = request.form.get('description', '').strip()
        sv.thumbnail_url = request.form.get('thumbnail_url', '').strip()
        sv.tags = request.form.get('tags', '').strip()
        sv.featured = 'featured' in request.form
        sv.active = 'active' in request.form
        sv.sort_order = request.form.get('sort_order', sv.sort_order, type=int)

        # Re-parse platform if URL changed
        platform, platform_id = _parse_social_url(sv.video_url)
        if platform and platform_id:
            sv.platform = platform
            sv.platform_id = platform_id

        # Update many-to-many
        all_video_ids = request.form.getlist('all_video_ids[]')
        sv.all_videos = AllVideo.query.filter(AllVideo.id.in_([int(x) for x in all_video_ids if x])).all() if all_video_ids else []

        db.session.commit()
        flash(f'Updated "{sv.title}".', 'success')
        return redirect(url_for('admin.view_social_videos'))

    return render_template('admin/edit_social_video.html', sv=sv, all_videos=all_videos)
