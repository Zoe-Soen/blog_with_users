import os
from datetime import date
from datetime import datetime as dt
from flask import Flask, render_template, redirect, url_for, flash, g, request, abort
from flask_bootstrap import Bootstrap
from flask_ckeditor import CKEditor
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from flask_gravatar import Gravatar # 用于给博客网站内添加用户头像的工具包
from functools import wraps
from forms import CreatePostForm, CommentForm, RegisterForm, LoginForm


TODAY = dt.now().strftime("%Y-%m-%d")
# ------------------------------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

# 实现富文本编辑：
ckeditor = CKEditor(app)
# 实现快速生成用户头像：
gravatar = Gravatar(
    app,
    size=100,
    rating="g",
    default="retro",
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None
)
Bootstrap(app)
# ------------------------------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
# ------------------------------------------------------------------------------------------------
##CONNECT TO DB
if os.environ.get('LOCAL') == True:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI_LOCAL')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('RENDER_DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = os.environ.get('SQLALCHEMY_TRACK_MODIFICATIONS')
db = SQLAlchemy(app)

# 定义 ORM 数据库模型：
# 1. 用户模型作为父表
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    name = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(50))

    # 通过 relationship() 来获取用户表中各 id 在 BlogPost 模型中所有 posts：
    posts_by_user = db.relationship("BlogPost", backref=db.backref("post_author_info"))
    comments_by_user = db.relationship("Comment", backref=db.backref("comment_author_info"))

# 2. 发帖模型作为子表：
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # 增加该字段，通过 ForeignKey 来指定用户表中的 id 字段进行外键关联：
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # 然后将 author 字段使用 User 模型中 posts 所定义的 backref 的内容，做相互间的关系映射：
    author = db.relationship("User", backref=db.backref("posts"))

    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)

    comments = db.relationship("Comment", backref=db.backref("parent_post"))

# 3. 评论模型作为子表：
class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # 外键关联作者字段：
    # 创建 relastionship 字段，映射 author 与 comments 之间的关系：
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    comment_author = db.relationship("User", backref=db.backref("all_comments"))
    # 外键关联对应的 post 信息：
    post_id = db.Column(db.Integer, db.ForeignKey("blog_posts.id"), nullable=False)
    post_name = db.relationship("BlogPost", backref=db.backref("all_comments"))
    text = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"{self.id},{self.comment_author}, commented to {self.post_id}:{self.post_name}."

with app.app_context():
    db.create_all()
# ------------------------------------------------------------------------------------------------

@app.route('/')
def get_all_posts():
    posts = BlogPost.query.all()
    return render_template("index.html", all_posts=posts, current_user=current_user)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data
        if db.session.query(User).filter(User.email == email).first():
            flash("You're already signed up! please log-in instead.")
            return redirect(url_for('login'))
        hashed_salted_pw = generate_password_hash(
            password=form.password.data,
            method="pbkdf2:sha256",
            salt_length=8
        )
        new_user=User(
            email = form.email.data,
            password = hashed_salted_pw,
            name = form.name.data,
            date = TODAY
        )
        with app.app_context():
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            return redirect(url_for("get_all_posts"))
        
    return render_template("register.html", form=form, current_user=current_user)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.query(User).filter(User.email == form.email.data).first()
        if not user:
            flash("The email does not exisit, please try again.")
            return redirect(url_for("login"))
        elif not check_password_hash(user.password, form.password.data):
            flash("Password incorrect, please try again.")
            return redirect(url_for("login"))
        else:
            login_user(user)
            return redirect(url_for("get_all_posts"))
    return render_template("login.html", form=form, current_user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    form = CommentForm()
    requested_post = BlogPost.query.get(post_id)

    if form.validate_on_submit():
        if not current_user.is_authenticated:
            flash("You need to login or register to comment.")
            return redirect(url_for('login'))
        
        # with app.app_context():
        db.session.add(Comment(
            text = form.comment_text.data,
            comment_author = current_user,
            post_name = requested_post,
            ))
        db.session.commit()

    return render_template("post.html", post=requested_post, form=form, current_user=current_user)


@app.route("/about")
def about():
    return render_template("about.html", current_user=current_user)


@app.route("/contact")
def contact():
    return render_template("contact.html", current_user=current_user)


# 创建一个装饰器：@admin_only
# 用来限制只有 admin（即：id=1）的用户才能操作的一些功能：add_new_post，edit_post，delete_posts
def admin_only(func):
    # @functools.wraps(func) 这个预置的装饰器可以帮助将函数名显示为被调用的函数名：add_new_post，edit_post，delete_posts，
    # 而非装饰器中的内置函数名：decorated_function
    @wraps(func)
    def decorated_function(*args, **kwargs):
        # 当用户尚未登陆时，即：current_user.is_authenticated 为 False，此时应重定向到 login 页面让用户登陆：
        if not current_user.is_authenticated:
            flash("This page is only available for admin, Please log in first.")
            return redirect(url_for('login'))
        # 当用户处于登陆状态，
        # 且 id!=1 时，返回 403（Forbidden） 错误：
        elif current_user.id != 1:
            return abort(403)
        # 否则则继续执行该路对应的视图函数（add_new_post，edit_post，delete_posts）：
        else:
            return func(*args, **kwargs)
    return decorated_function

@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        new_post = BlogPost(
            title = form.title.data,
            subtitle = form.subtitle.data,
            body = form.body.data,
            img_url = form.img_url.data,
            author = current_user,
            date = date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form, current_user=current_user)


@app.route("/edit-post/<int:post_id>")
@admin_only
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
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
        post.author = edit_form.author.data
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))

    return render_template("make-post.html", form=edit_form, current_user=current_user)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = BlogPost.query.get(post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


# ------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
