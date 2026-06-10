from flask import jsonify, render_template

from . import sports_bp
from .serializers import compact_match_payload, detailed_match_payload
from .services import (
    get_competition_standings,
    get_enabled_competitions,
    get_featured_matches,
    get_live_match_states,
    get_match_events,
    get_match_state,
)
from .stream_resolver import resolve_demo_stream, resolve_stream
from ..models import SportsCompetition, SportsMatch


@sports_bp.route("/")
def index():
    matches = get_featured_matches()
    live_matches = get_live_match_states()
    competitions = get_enabled_competitions("football")
    return render_template(
        "sports/index.html",
        matches=matches,
        live_matches=live_matches,
        competitions=competitions,
        active_sport="football",
        dark=True,
        show_top_banner=False,
    )


@sports_bp.route("/football")
def football():
    return index()


@sports_bp.route("/<sport_slug>")
def sport_home(sport_slug):
    matches = get_featured_matches()
    competitions = get_enabled_competitions(sport_slug)
    return render_template(
        "sports/index.html",
        matches=matches,
        live_matches=get_live_match_states(),
        competitions=competitions,
        active_sport=sport_slug,
        dark=True,
        show_top_banner=False,
    )


@sports_bp.route("/<sport_slug>/competitions/<competition_slug>")
def competition_detail(sport_slug, competition_slug):
    competition = SportsCompetition.query.filter_by(slug=competition_slug, hidden=False).first_or_404()
    matches = (
        SportsMatch.query
        .filter_by(competition_id=competition.id, archived=False)
        .order_by(SportsMatch.kickoff_at.asc().nullslast())
        .limit(40)
        .all()
    )
    standings = (
        SportsStanding.query
        .filter_by(competition_id=competition.id)
        .order_by(SportsStanding.group_name.asc().nullslast(), SportsStanding.position.asc().nullslast())
        .limit(80)
        .all()
    )
    return render_template(
        "sports/competition.html",
        competition=competition,
        matches=matches,
        standings=standings,
        active_sport=sport_slug,
        dark=True,
        show_top_banner=False,
    )


@sports_bp.route("/match/<int:match_id>")
def match_detail(match_id):
    match_state = get_match_state(match_id)
    match = SportsMatch.query.get_or_404(match_id)
    stream = resolve_stream(match)
    return render_template(
        "sports/match.html",
        match=match,
        match_state=match_state,
        stream=stream,
        dark=True,
        show_top_banner=False,
    )


@sports_bp.route("/match/<int:match_id>/watch")
def watch_match(match_id):
    match = SportsMatch.query.get_or_404(match_id)
    stream = resolve_stream(match)
    match_state = get_match_state(match_id)
    return render_template(
        "sports/watch.html",
        match=match,
        match_state=match_state,
        stream=stream,
        dark=True,
        show_top_banner=False,
    )


@sports_bp.route("/api/live-matches")
def api_live_matches():
    return jsonify({
        "success": True,
        "matches": [compact_match_payload(match) for match in get_live_match_states()],
    })


@sports_bp.route("/api/match/<int:match_id>")
def api_match(match_id):
    return jsonify({
        "success": True,
        "match": detailed_match_payload(get_match_state(match_id)),
    })


@sports_bp.route("/api/match/<int:match_id>/events")
def api_match_events(match_id):
    return jsonify({
        "success": True,
        "events": get_match_events(match_id),
    })


@sports_bp.route("/api/competition/<int:competition_id>/standings")
def api_competition_standings(competition_id):
    return jsonify({
        "success": True,
        "standings": get_competition_standings(competition_id),
    })


@sports_bp.route("/api/watch-demo")
def api_watch_demo():
    return jsonify({"success": True, "stream": resolve_demo_stream()})
