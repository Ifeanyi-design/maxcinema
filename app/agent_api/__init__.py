from flask import Blueprint

agent_api_bp = Blueprint("agent_api", __name__, url_prefix="/api/agent/v1")

from . import routes  # noqa: E402,F401
