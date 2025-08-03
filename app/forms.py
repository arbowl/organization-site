"""Forms"""

from flask_login import current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional

from app.models import User


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember Me")
    submit = SubmitField("Log In")


class RegistrationForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField("Repeat Password", validators=[DataRequired()])
    submit = SubmitField("Register")

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError("Username already taken. Please choose a different one.")

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError("Email already registered. Please use a different address.")


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=140)])
    content = TextAreaField("Content", validators=[DataRequired()])
    submit = SubmitField("Publish")


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


class SearchForm(FlaskForm):
    q = StringField("Search", validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField("Go")
