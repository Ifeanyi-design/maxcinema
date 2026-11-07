import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import current_app, g, jsonify, request
from sqlalchemy import and_, update
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models import AgentAccessToken, AgentPairingCode


DEFAULT_AGENT_SCOPES = ["content:read", "content:write", "links:write"]


def hash_secret(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_pairing_code(created_by_id):
    """Create a one-time, high-entropy pairing code valid for ten minutes."""
    raw_code = secrets.token_urlsafe(18)
    now = datetime.utcnow()
    row = AgentPairingCode(
        code_hash=hash_secret(raw_code),
        created_by_id=created_by_id,
        created_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    db.session.add(row)
    db.session.commit()
    return raw_code, row


def exchange_pairing_code(raw_code, label=None):
    """Consume a pairing code once and return a newly-issued bearer token."""
    code = (raw_code or "").strip()
    if not code or len(code) > 128:
        return None, "A valid pairing code is required."

    now = datetime.utcnow()
    try:
        pairing = AgentPairingCode.query.filter_by(
            code_hash=hash_secret(code)
        ).first()
        if pairing is None:
            db.session.rollback()
            return None, "The pairing code is invalid, expired, or already used."

        # Atomic conditional claim prevents two concurrent exchanges (including
        # on SQLite, where SELECT FOR UPDATE is not a row lock) from both winning.
        claimed = db.session.execute(
            update(AgentPairingCode)
            .where(
                and_(
                    AgentPairingCode.id == pairing.id,
                    AgentPairingCode.used_at.is_(None),
                    AgentPairingCode.expires_at > now,
                )
            )
            .values(used_at=now)
        )
        if claimed.rowcount != 1:
            db.session.rollback()
            return None, "The pairing code is invalid, expired, or already used."

        token_value = "mca_" + secrets.token_urlsafe(36)
        safe_label = label.strip() if isinstance(label, str) else "Content management agent"
        token_row = AgentAccessToken(
            token_hash=hash_secret(token_value),
            label=(safe_label or "Content management agent")[:120],
            scopes=list(DEFAULT_AGENT_SCOPES),
            created_by_id=pairing.created_by_id,
            created_at=now,
            expires_at=now + timedelta(minutes=60),
        )
        db.session.add(token_row)
        db.session.commit()
        return {
            "access_token": token_value,
            "token_type": "Bearer",
            "expires_at": token_row.expires_at.isoformat() + "Z",
            "scopes": list(DEFAULT_AGENT_SCOPES),
        }, None
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Agent pairing exchange failed")
        return None, "Could not complete pairing. Generate a new code and try again."


def agent_required(scope):
    """Require a live bearer token with the requested scope."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            scheme, _, credential = header.partition(" ")
            if scheme.lower() != "bearer" or not credential.startswith("mca_"):
                return jsonify({
                    "error": "unauthorized",
                    "message": "Send the agent access token as an Authorization: Bearer header.",
                }), 401

            token_row = AgentAccessToken.query.filter_by(
                token_hash=hash_secret(credential)
            ).first()
            now = datetime.utcnow()
            if (
                token_row is None
                or token_row.revoked_at is not None
                or token_row.expires_at <= now
            ):
                return jsonify({
                    "error": "invalid_or_expired_token",
                    "message": "The agent session is invalid, expired, or revoked. Pair again.",
                }), 401

            scopes = token_row.scopes or []
            if scope not in scopes:
                return jsonify({
                    "error": "insufficient_scope",
                    "required_scope": scope,
                }), 403

            token_row.last_used_at = now
            db.session.commit()
            g.agent_token = token_row
            return view(*args, **kwargs)
        return wrapped
    return decorator


def write_audit(action, target_type, target_id, details=None):
    """Write a minimal audit entry; never store bearer tokens or download codes."""
    from ..models import AgentAuditLog

    row = AgentAuditLog(
        agent_token_id=getattr(getattr(g, "agent_token", None), "id", None),
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
        created_at=datetime.utcnow(),
    )
    db.session.add(row)
