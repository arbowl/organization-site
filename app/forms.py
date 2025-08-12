"""Forms"""

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
    Field,
)
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional

from app.models import User, Post


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
    submit = SubmitField("Publish")

    def validate_title(self, field: Field):
        slug = slugify(field.data)
        if Post.query.filter_by(slug=slug).first():
            raise ValidationError(
                "That title has already been used; please choose another."
            )


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
