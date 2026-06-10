from flask import Blueprint


sports_bp = Blueprint(
    "sports",
    __name__,
    url_prefix="/sports",
    template_folder="../templates/sports",
)


from . import routes

