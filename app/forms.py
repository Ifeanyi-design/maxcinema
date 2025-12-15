import json

from .extensions import db
from .models import User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating, Trailer, StorageServer, RecentItem

app = create_app()
app.app_context().push()

tables = [User, Genre, AllVideo, Movie, Series, Season, Episode, Comment, Rating, Trailer, StorageServer, RecentItem]

for table in tables:
    data = []
    for row in table.query.all():
        row_dict = {c.name: getattr(row, c.name) for c in row.__table__.columns}
        data.append(row_dict)
    with open(f"{table.__tablename__}_backup.json", "w", encoding="utf-8") as f:
        json.dump(data, f, default=str, ensure_ascii=False, indent=2)

print("All tables exported to JSON files successfully.")
