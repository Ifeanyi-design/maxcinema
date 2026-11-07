import hashlib
import secrets
from datetime import datetime, timedelta

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import admin_bp
from .helpers import admin_required
from ..extensions import db
from ..models import AgentAccessToken, AgentPairingCode


@admin_bp.route("/agent-access", methods=["GET", "POST"])
@login_required
@admin_required
def agent_access():
    pairing_code = None
    if request.method == "POST":
        pairing_code = secrets.token_urlsafe(18)
        now = datetime.utcnow()
        row = AgentPairingCode(
            code_hash=hashlib.sha256(pairing_code.encode("utf-8")).hexdigest(),
            created_by_id=current_user.id,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        db.session.add(row)
        db.session.commit()
        flash("Pairing code generated. It is shown only once and expires in 10 minutes.", "success")

    tokens = AgentAccessToken.query.order_by(AgentAccessToken.created_at.desc()).limit(30).all()
    now = datetime.utcnow()
    return render_template(
        "admin/agent_access.html",
        pairing_code=pairing_code,
        tokens=tokens,
        now=now,
    )


@admin_bp.route("/agent-access/tokens/<int:token_id>/revoke", methods=["POST"])
@login_required
@admin_required
def revoke_agent_token(token_id):
    token = AgentAccessToken.query.get_or_404(token_id)
    if token.revoked_at is None:
        token.revoked_at = datetime.utcnow()
        db.session.commit()
        flash("Agent session revoked.", "success")
    else:
        flash("That session was already revoked.", "warning")
    return redirect(url_for("admin.agent_access"))
