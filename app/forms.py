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
    SelectMultipleField,
)
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional, URL

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
    tags = StringField(
        "Tags (comma-separated)", validators=[Optional(), Length(max=200)]
    )
    save_draft = SubmitField("Save Draft")
    submit = SubmitField("Done")

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


class BillCommentForm(FlaskForm):
    """Form for commenting on bills"""
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


class BioForm(FlaskForm):
    """Form for editing user bio information"""
    bio_text = TextAreaField(
        "Bio", 
        validators=[Optional(), Length(max=1000)],
        render_kw={"placeholder": "Tell us about yourself... (Markdown supported)", "rows": 6}
    )
    location = StringField(
        "Location", 
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "e.g., Boston, MA"}
    )
    website = StringField(
        "Website", 
        validators=[Optional(), Length(max=200), URL(message="Please enter a valid URL")],
        render_kw={"placeholder": "https://yourwebsite.com"}
    )
    favorite_tags = SelectMultipleField(
        "Favorite Tags (up to 3)",
        validators=[Optional()],
        coerce=int,
        render_kw={"size": 10}
    )
    submit = SubmitField("Save Bio")

    def validate_website(self, field):
        if field.data and not field.data.startswith(('http://', 'https://')):
            field.data = 'https://' + field.data

    def validate_bio_text(self, field):
        if field.data:
            # Check for potentially harmful content
            bio_text = field.data.strip()
            if len(bio_text) > 1000:
                raise ValidationError("Bio text cannot exceed 1000 characters.")
            
            # Basic content validation
            if bio_text.count('<script') > 0 or bio_text.count('javascript:') > 0:
                raise ValidationError("Bio text contains potentially harmful content.")

    def validate_favorite_tags(self, field):
        if field.data and len(field.data) > 3:
            raise ValidationError("You can select at most 3 favorite tags.")


class NewsletterForm(FlaskForm):
    """Form for guest newsletter subscription"""
    email = StringField(
        "Email", 
        validators=[DataRequired(), Email(), Length(1, 120)],
        render_kw={"placeholder": "Enter your email address", "class": "w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"}
    )
    submit = SubmitField(
        "Subscribe", 
        render_kw={"class": "w-full bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-4 rounded-md transition duration-300"}
    )


class ChangePasswordForm(FlaskForm):
    """Form for changing user password"""
    current_password = PasswordField(
        "Current Password",
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter your current password"}
    )
    new_password = PasswordField(
        "New Password",
        validators=[DataRequired(), Length(min=6, message="Password must be at least 6 characters long")],
        render_kw={"placeholder": "Enter new password (minimum 6 characters)"}
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[DataRequired()],
        render_kw={"placeholder": "Confirm new password"}
    )
    submit = SubmitField("Change Password")

    def validate_confirm_password(self, field):
        if field.data != self.new_password.data:
            raise ValidationError("Passwords do not match.")
