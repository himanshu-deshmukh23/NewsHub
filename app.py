from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_wtf import FlaskForm
from newsapi.newsapi_client import NewsApiClient
import pandas
from wtforms import StringField, PasswordField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from datetime import date, timedelta
from celery import Celery
from celery.schedules import crontab

app = Flask(__name__)
celery = Celery(__name__, broker='redis://localhost:6379/0')

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
api_key = '70b1d917f8ea45c883fc4f9ca27a6c94'

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = 'your_username'
app.config['MAIL_PASSWORD'] = 'your_password'
app.config['MAIL_USE_TLS'] = True

mail = Mail(app)
newsapi = NewsApiClient(api_key=api_key)

# User authentication configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# Database models
class UserX(UserMixin, db.Model):
    __tablename__ = 'userx'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    subscribed_topic = db.Column(db.String(50))


# User registration and login forms
class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])


class TopicSelectionForm(FlaskForm):
    topic = SelectField('Topic', choices=[('Government of India', 'Topic 1'), ('NASA', 'Topic 2'),
                                          ('Python AI', 'Topic 3')])


celery.conf.beat_schedule = {
    'send-daily-news': {
        'task': 'News_app.tasks.send_news_updates',
        'schedule': crontab(hour=8, minute=0),
    },
}


@login_manager.user_loader
def load_user(user_id):
    return UserX.query.get(int(user_id))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = UserX(email=form.email.data, password=form.password.data)
        db.session.add(user)
        db.session.commit()
        return "Registration successful! You can now <a href='/login'>login</a>."
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = UserX.query.filter_by(email=form.email.data).first()
        if user and user.password == form.password.data:
            login_user(user)
            return "Login successful! You can now <a href='/profile'>view your profile</a>."
        return "Invalid email or password."
    return render_template('login.html', form=form)


@app.route('/profile')
@login_required
def profile():
    form = TopicSelectionForm()
    return render_template('profile.html', form=form)


@app.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    form = TopicSelectionForm(request.form)

    if form.validate():
        selected_topic = form.topic.data
        current_user.subscribed_topic = selected_topic
        db.session.commit()

        flash(f'Successfully subscribed to {selected_topic}!', 'success')
    else:
        flash('Invalid form submission. Please try again.', 'danger')

    return redirect(url_for('profile'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


def get_news(topic):
    curr_date = date.today() - timedelta(1)
    data = newsapi.get_everything(q=topic, from_param=curr_date)
    articles = data['articles']
    news_df = pandas.DataFrame(articles).dropna()
    return news_df


@celery.task
def send_daily_news_email(user_email, topics):
    # Fetch news related to the subscribed topics
    # Construct an email with the news content
    # Send the email to the user's email address

    msg = Message('Your Daily News', recipients=[user_email])
    msg.body = "Here are the latest news related to your subscribed topics..."
    # Add news content to the email

    mail.send(msg)


def send_news_updates():
    users = UserX.query.all()
    user_topics = {}
    for user in users:
        for topic in user.subscribed_topics:
            if topic.name not in user_topics:
                user_topics[topic.name] = []
            user_topics[topic.name].append(user)

    for topic, users in user_topics.items():
        news_data = get_news(topic)
        email_content = "Here are the latest news on your subscribed topic: " + '\n' + news_data[0]['content'] + '\n' + news_data[0]['url']
        for user in users:
            send_email(user.email, "Today's News Update", email_content)


def send_email(recipient, subject, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    mail.send(msg)


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
