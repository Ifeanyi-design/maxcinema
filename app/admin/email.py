"""Admin email tools — compose, send, and track emails."""

from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user

from . import admin_bp
from .helpers import admin_required, _send_email_notification, _get_email_provider_config, _email_transport_status
from ..models import User, EmailHistory, db


@admin_bp.route("/email", methods=["GET", "POST"])
@login_required
@admin_required
def email_compose():
    """Compose and send an email."""
    cfg = _get_email_provider_config()
    enabled, provider = _email_transport_status(cfg)

    users = User.query.order_by(User.email).all()

    if request.method == "POST":
        recipient_mode = request.form.get("recipient_mode", "single").strip()
        to_email = request.form.get("to_email", "").strip()
        custom_email = request.form.get("custom_email", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        template_name = request.form.get("template", "")

        if recipient_mode == "all":
            to_email = "__ALL_USERS__"
        elif recipient_mode == "custom":
            to_email = custom_email

        if not to_email or not subject or not body:
            flash("To, subject, and body are required.", "danger")
            return redirect(url_for("admin.email_compose"))

        if to_email == "__ALL_USERS__":
            sent_count = 0
            fail_count = 0
            for user in users:
                user_body = body.replace("{username}", user.username or user.email)
                user_subject = subject.replace("{username}", user.username or user.email)

                html_body = None
                if template_name:
                    try:
                        html_body = render_template(
                            f"emails/{template_name}.html",
                            subject=user_subject,
                            body=user_body,
                            site_url=url_for("main.index", _external=True),
                        )
                    except Exception:
                        pass

                success, error = _send_email_notification(user.email, user_subject, user_body, html_body)
                record = EmailHistory(
                    to_email=user.email,
                    subject=user_subject,
                    body=user_body,
                    status="sent" if success else "failed",
                    error_message=error if not success else None,
                    sent_by=getattr(current_user, "email", "admin"),
                )
                db.session.add(record)
                if success:
                    sent_count += 1
                else:
                    fail_count += 1

            db.session.commit()
            flash(f"Batch email: {sent_count} sent, {fail_count} failed.", "success" if fail_count == 0 else "warning")
        else:
            body = body.replace("{username}", to_email.split("@")[0])
            subject = subject.replace("{username}", to_email.split("@")[0])

            html_body = None
            if template_name:
                try:
                    html_body = render_template(
                        f"emails/{template_name}.html",
                        subject=subject,
                        body=body,
                        site_url=url_for("main.index", _external=True),
                    )
                except Exception:
                    pass

            success, error = _send_email_notification(to_email, subject, body, html_body)

            record = EmailHistory(
                to_email=to_email,
                subject=subject,
                body=body,
                status="sent" if success else "failed",
                error_message=error if not success else None,
                sent_by=getattr(current_user, "email", "admin"),
            )
            db.session.add(record)
            db.session.commit()

            if success:
                flash(f"Email sent to {to_email}", "success")
            else:
                flash(f"Failed to send: {error}", "danger")

        return redirect(url_for("admin.email_compose"))

    history = EmailHistory.query.order_by(EmailHistory.sent_at.desc()).limit(50).all()
    return render_template(
        "admin/email.html",
        users=users,
        history=history,
        email_enabled=enabled,
        email_provider=provider,
    )


@admin_bp.route("/email/history")
@login_required
@admin_required
def email_history():
    """View email history (JSON endpoint for AJAX)."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = EmailHistory.query.order_by(
        EmailHistory.sent_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "emails": [
            {
                "id": e.id,
                "to_email": e.to_email,
                "subject": e.subject,
                "status": e.status,
                "error_message": e.error_message,
                "sent_by": e.sent_by,
                "sent_at": e.sent_at.isoformat() if e.sent_at else None,
            }
            for e in pagination.items
        ],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page,
    })
