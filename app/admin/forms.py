from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, BooleanField, IntegerField, 
    FloatField, SelectField, SelectMultipleField, DateField, SubmitField, URLField, PasswordField
)
from wtforms.validators import DataRequired, Optional, NumberRange, Length

class AllVideoForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    slug = StringField("Slug", validators=[Optional()])
    description = TextAreaField("Description", validators=[Optional()])
    year_produced = IntegerField("Year Produced", validators=[Optional()])
    length = StringField("Length", validators=[Optional()])
    rating = FloatField("Rating", validators=[Optional()])
    country = StringField("Country", validators=[Optional()])
    language = StringField("Language", validators=[Optional()])
    subtitles = StringField("Subtitles", validators=[Optional()])
    released_date = DateField(
        "Released Date",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    star_cast = TextAreaField("Star Cast", validators=[Optional()])
    source = StringField("Source URL", validators=[Optional()])
    image = StringField("Image Poster", validators=[Optional()])
    download_link = StringField("Download URL", validators=[Optional()])
    trailer_url = StringField("Trailer URL", validators=[Optional()])

    # Checkbox fields
    featured = BooleanField("Featured")
    trending = BooleanField("Trending")
    active = BooleanField("Active")

    # Movie / Series switcher
    type = SelectField(
        "Type",
        choices=[("movie", "Movie"), ("series", "Series")],
        validators=[DataRequired()]
    )

    # Many-to-many Genre checkboxes
    genres = SelectMultipleField(
        "Genres",
        coerce=int,
        validators=[Optional()]
    )

    # Storage server dropdown
    storage_server_id = SelectField(
        "Storage Server",
        coerce=int,
        validators=[Optional()]
    )

    submit = SubmitField("Save Changes")



class SeasonForm(FlaskForm):
    season_number = IntegerField(
        "Season Number",
        validators=[DataRequired(), NumberRange(min=1)],
        render_kw={"placeholder": "e.g. 1"}
    )
    
    
    description = TextAreaField(
        "Description",
        validators=[Optional(), Length(max=2000)],
        render_kw={"placeholder": "Brief synopsis of this season"}
    )
    
    cast = TextAreaField(
        "Cast",
        validators=[Optional(), Length(max=1000)],
        render_kw={"placeholder": "Comma-separated list of cast names"}
    )
    
    completed = BooleanField("Completed")
    
    
    release_date = DateField(
        "Release Date",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    
    image = StringField(
        "Cover Image URL",
        validators=[Optional(), Length(max=300)],
        render_kw={"placeholder": "URL to season poster"}
    )
    
    trailer_url = URLField(
        "Trailer URL",
        validators=[Optional(), Length(max=300)],
        render_kw={"placeholder": "URL to season trailer"}
    )
    
    submit = SubmitField("Save Season")



class EpisodeForm(FlaskForm):
    episode_number = IntegerField(
        "Episode Number",
        validators=[DataRequired(), NumberRange(min=1)],
        render_kw={"placeholder": "e.g. 1"}
    )
    name = StringField("Name", validators=[DataRequired()], render_kw={"placeholder": "Title of Episode"})
    length = StringField("Length", validators=[Optional()])
    description = TextAreaField(
        "Description", validators=[Optional()],
        render_kw={"placeholder": "Brief synopsis of this season"})
    cast = TextAreaField(
        "Cast",
        validators=[Optional(), Length(max=1000)],
        render_kw={"placeholder": "Comma-separated list of cast names"}
    )
    released_date = DateField(
        "Released Date",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    source = StringField("Source URL", validators=[Optional()])
    download_link = StringField("Download URL", validators=[Optional()])
    storage_server_id = SelectField(
        "Storage Server",
        coerce=int,
        validators=[Optional()]
    )
    submit = SubmitField("Save Episode")


class TrailerForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()], render_kw={"placeholder": "Title of Trailer"})
    slug = StringField("Slug", validators=[Optional()], render_kw={"placeholder": "seo friendly title e.g. wonda-man"})
    trailer_link = StringField("Trailer URL", validators=[Optional()])
    image = StringField("Image Poster", validators=[Optional()])
    description = TextAreaField(
        "Description", validators=[Optional()],
        render_kw={"placeholder": "Brief synopsis of this season"})
    release_date = DateField(
        "Release Date",
        format="%Y-%m-%d",
        validators=[Optional()],
        render_kw={"placeholder": "YYYY-MM-DD"}
    )
    release_year = IntegerField("Year Produced", validators=[Optional()], render_kw={"placeholder": "e.g. 2025"})
    submit = SubmitField("Save Trailer")

class UserForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()], render_kw={"placeholder": "Enter username"})
    email = StringField("Email", validators=[DataRequired()], render_kw={"placeholder": "Enter email address"})
    is_admin = BooleanField("Admin Privileges")
    password_hash = StringField("Password", validators=[Optional()], render_kw={"placeholder": "Enter new password"})    
    submit = SubmitField("Save User")

class StorageServerForm(FlaskForm):
    name = StringField('Server Name', validators=[
        DataRequired(), 
        Length(min=2, max=100)
    ])
    
    server_type = SelectField('Server Type', choices=[
        ('local', 'Local Server / Folder'),
        ('aws_s3', 'AWS S3 Bucket'),
        ('bytescale', 'Bytescale / Cloud Image'),
        ('ftp', 'FTP Server'),
        ('terabox', 'Terabox'),
        ('streamwish', 'StreamWish'),
        ('doodstream', 'DoodStream'),
        ('1fichier', '1Fichier'),
        ('gofile', 'GoFile'), 
        ('pixeldrain', 'PixelDrain'),
        ('telegram', 'Telegram')
    ], validators=[DataRequired()])
    
    base_url = StringField('Base URL / Path', validators=[
        DataRequired(),
        Length(max=255)
    ], description="http://myserver.com/files or C:/videos/")

    # Credentials (Optional because local folders might not need them)
    api_key = StringField('API Key', validators=[Optional(), Length(max=255)])
    username = StringField('Username', validators=[Optional(), Length(max=100)])
    password = PasswordField('Password', validators=[Optional(), Length(max=100)])
    
    # Storage settings
    max_storage_gb = FloatField('Max Storage (GB)', validators=[
        Optional(),
        NumberRange(min=0, message="Storage cannot be negative.")
    ], default=100.0, description="Set to 0 for unlimited.")
    used_storage_gb = FloatField('Used Storage (GB)', validators=[
        Optional(),
        NumberRange(min=0, message="Storage cannot be negative.")
    ], default=100.0, description="Set to 0 for unlimited.")
    
    active = BooleanField('Active', default=True, description="Uncheck to disable uploads to this server.")
    
    submit = SubmitField('Save Server')