import datetime
from datetime import date
from flask import Flask, render_template, redirect, url_for, flash
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
ckeditor = CKEditor(app)
Bootstrap5(app)

login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@app.context_processor
def current_year():
    """For dynamically inserting the current year into the footer"""
    return {'current_year': datetime.datetime.now().year}


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///posts.db'
db = SQLAlchemy(model_class=Base)
db.init_app(app)


class BlogPost(db.Model):  # child
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))  # foreign key
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    # relationships
    author = relationship("User", back_populates='posts')
    comments = relationship('Comment', back_populates='parent_post')


class User(UserMixin, db.Model):  # parent
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False)

    # relationships
    posts = relationship("BlogPost", back_populates="author")
    comments = relationship('Comment', back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))  # link comment to author id
    post_id: Mapped[str] = mapped_column(Integer, db.ForeignKey('blog_posts.id'))  # link comment to post id
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # relationships
    parent_post = relationship('BlogPost', back_populates='comments')
    comment_author = relationship("User", back_populates='comments')


with app.app_context():
    db.create_all()


def admin_required(func):
    @wraps(func)
    def decorated_view(*args, **kwargs):

        if not current_user.is_authenticated:
            flash('You must be Admin to access this page')
            return redirect(url_for('get_all_posts'))

        if current_user.id != 1:
            flash("You must be logged in to access this page")
            return redirect(url_for('login'))

        return func(*args, **kwargs)

    return decorated_view


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()  # search if user already exists in db

        if user:
            flash('User already exists, please login!')
            return redirect(url_for('login'))  # if existing email, redirect to login page

        new_user = User(  # if user with that email does not exist, create new user
            name=form.name.data,
            email=form.email.data,
            password=generate_password_hash(password=form.password.data, method='pbkdf2:sha256', salt_length=8)
        )

        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)  # logs the new user in before redirect
        return redirect(url_for('get_all_posts'))  # redirect new user to home

    return render_template("register.html", form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()  # search db to check if user with email exists

        if not user:
            flash('User does not exist, please register!')
            return redirect(url_for('register'))  # if email does not exist, send user to register
        if user and not check_password_hash(user.password, form.password.data):
            flash('Incorrect Email or Password!')
            return redirect(url_for('login'))
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('get_all_posts'))

    return render_template("login.html", form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = BlogPost.query.options(
        db.joinedload(BlogPost.comments).joinedload(Comment.comment_author)
    ).get(post_id)
    if form.validate_on_submit():  # if a comment is submitted
        if not current_user.is_authenticated:  # if user not login/registered redirect them to do so
            flash('Please login or register to post comments')
            return redirect(url_for('login'))

        if not form.body.data == "":
            comment = Comment(  # otherwise add comment to db
                author_id=current_user.id,
                post_id=requested_post.id,
                text=form.body.data
            )
            db.session.add(comment)
            db.session.commit()
            redirect(url_for('show_post', post_id=post_id))

    return render_template("post.html", post=requested_post, form=form)


@app.route("/new-post", methods=["GET", "POST"])
@login_required
@admin_required
def add_new_post():
    form = CreatePostForm()

    if form.validate_on_submit():
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user.name
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@login_required
@admin_required
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run(debug=True, port=5002)
