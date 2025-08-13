"""Forms"""

import re

from flask_login import current_user
from flask_wtf import FlaskForm
from slugify import slugify
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
    TextAreaField,
    HiddenField,
)
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional

from app.models import User, Post

TAG_RE = re.compile(r"^[a-z0-9][a-z0-9\- ]{0,38}[a-z0-9]$", re.I)


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Log In")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=25)]
    )
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField("Repeat Password", validators=[DataRequired()])
    newsletter = BooleanField("Subscribe to our weekly newsletter", default=False)
    submit = SubmitField("Register")

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError(
                "Username already taken. Please choose a different one."
            )

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError(
                "Email already registered. Please use a different address."
            )


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=140)])
    content = TextAreaField("Content", validators=[DataRequired()])
    tags = StringField('Tags (comma-separated)', validators=[Optional(), Length(max=200)])
    submit = SubmitField("Publish")

    def __init__(self, *args, post_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.post_id = post_id

    def validate_title(self, field):
        slug = slugify(field.data)
        q = Post.query.filter_by(slug=slug)
        if self.post_id:
            q = q.filter(Post.id != self.post_id)
        if q.first():
            raise ValidationError(
                "That title has already been used; please choose another."
            )

    def clean_tags(self):
        raw = (self.tags.data or "").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) > 5:
            raise ValidationError("Please add at most 5 tags.")
        cleaned = []
        for p in parts:
            if not TAG_RE.match(p):
                raise ValidationError(f"Tag '{p}' has invalid characters.")
            cleaned.append(p.lower())
        seen = set()
        deduped = [t for t in cleaned if not (t in seen or seen.add(t))]
        return deduped


class CommentForm(FlaskForm):
    post_id = HiddenField(validators=[DataRequired()])
    parent_id = HiddenField()
    guest_name = StringField("Name", validators=[Optional(), Length(1, 80)])
    content = TextAreaField("Comment", validators=[DataRequired(), Length(max=5000)])
    submit = SubmitField("Post Comment")

    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False
        if not current_user.is_authenticated:
            if not self.guest_name.data.strip():
                self.guest_name.errors.append("Name required for guest comments.")
                return False
        return True


class CommentEditForm(FlaskForm):
    comment_id = HiddenField(validators=[DataRequired()])
    content = TextAreaField(
        "Edit your comment", validators=[DataRequired(), Length(min=1, max=5000)]
    )
    submit = SubmitField("Save")


class SearchForm(FlaskForm):
    q = StringField("Search", validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField("Go")


class ContactForm(FlaskForm):
    name = StringField("Your name", validators=[DataRequired(), Length(1, 80)])
    email = StringField(
        "Your email", validators=[DataRequired(), Email(), Length(1, 200)]
    )
    subject = StringField("Subject", validators=[DataRequired(), Length(1, 120)])
    message = TextAreaField("Message", validators=[DataRequired(), Length(1, 5000)])
    submit = SubmitField("Send Message")
