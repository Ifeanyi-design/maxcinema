from flask import Blueprint

admin_bp = Blueprint(
    "admin",
    __name__,
    url_prefix="/admin",
    template_folder="templates"
)

from . import views
from . import movies
from . import series
from . import trailers
from . import users
from . import storage
from . import notifications
from . import analytics
from . import polls
from . import leads
from . import content
from . import email
from . import backup
from . import social_videos
