import os
import re
import random
import hashlib
import hmac
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)

secret = 'fart'


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)


class MainPage(BlogHandler):
    def get(self):
        self.render('welcome.html')


# user stuff
def make_salt(length=5):
    """
    make salt
    Args:
        Length of 5
    Returns:
        returns a string with 5 random letters
    """
    return ''.join(random.choice(letters) for x in xrange(length))


def make_pw_hash(name, pw, salt=None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)


def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)


def users_key(group='default'):
    return db.Key.from_path('users', group)


class User(db.Model):
    """
    User Model
    Attr:
        name, password, email
    """
    name = db.StringProperty(required=True)
    pw_hash = db.StringProperty(required=True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent=users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent=users_key(),
                    name=name,
                    pw_hash=pw_hash,
                    email=email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


# blog stuff

def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


class Post(db.Model):
    subject = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    author = db.ReferenceProperty(User)
    likes = db.IntegerProperty(default=0)
    dislikes = db.IntegerProperty(default=0)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p=self)


class Comment(db.Model):
    post = db.ReferenceProperty(Post)
    content = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    author = db.ReferenceProperty(User)


class BlogFront(BlogHandler):
    """
    Front Page of Blog
        Only shows posts not comments
    """

    def get(self):
        posts = greetings = Post.all().order('-created')
        # comments = Comment.all().order('-created')
        self.render('front.html', posts=posts)


class PostPage(BlogHandler):
    """
    Post page includes posts and comments
    """

    def get(self, post_id):
        post_key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(post_key)
        if not post:
            self.error(404)
            return
        print post.content
        comments = Comment.all().filter('post =', post_key)

        self.render("permalink.html", post=post, comments=comments)


class NewPost(BlogHandler):
    """
    Create a new post
    """
    def get(self):
        """
        if user is logged in,
        render new post template
        """
        if self.user:
            author = self.user.key()
            self.render("newpost.html", author=author)
        else:
            return self.redirect("/login")

    def post(self):
        """
        if user is not logged in redirect to blog
        """
        if not self.user:
            return self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')
        author = self.user.key()


        if subject and content:
            p = Post(parent=blog_key(), subject=subject,
                     content=content, author=author)
            p.put()
            return self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject,
                        content=content, error=error, author=author)


class EditPost(BlogHandler):
    def get(self, post_id):
        """
        get the post by id
        check if current user is the author
        """
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            if self.user:
                if post.author.key().id() != self.user.key().id():
                    return self.redirect('/blog/%s' % str(post.key().id()))
                else:
                    self.render("editpost.html",
                                subject=post.subject, content=post.content)
            else:
                error = 'You must be logged in to edit post.'
                self.render('login-form.html', error=error)
        else:
            self.write("post not found")

    def post(self, post_id):
        if not self.user:
            return self.redirect('/blog')
        if post.author.key().id() != self.user.key().id():
            return self.redirect('/blog/%s' % str(post.key().id()))
        else:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            subject = self.request.get('subject')
            content = self.request.get('content')

            if subject and content:
                post.subject = subject
                post.content = content
                post.put()
                return self.redirect('/blog')
            else:
                error = "subject and content, please!"
                self.render("editpost.html", subject=subject,
                            content=content, error=error)


class DeletePost(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if not post:
            self.error(404)
            return
        if self.user:
            self.render("deletepost.html", post=post)
        else:
            error = 'You must be logged in to delete this post.'
            self.render('login-form.html', error=error)

    def post(self, post_id):
        if not self.user:
            return self.redirect('/login')
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if post and (post.author.key() == self.user.key()):
            db.delete(post)
        return self.redirect('/blog')


class LikePost(BlogHandler):
    def get(self, post_id):
        if not self.user:
            error = 'You must be logged in to like this post'
            return self.render('login-form.html', error=error)
        post_key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(post_key)
        comments = Comment.all().filter('post =', post_key)
        if self.user.key() == post.author.key():
            error = 'You can not like your own post.'
            self.render('permalink.html', post=post, comments=comments,
                        error=error)
        else:
            if post:
                post.likes += 1
                post.put()
                return self.redirect('/blog/%s' % post_id)


class DislikePost(BlogHandler):
    def get(self, post_id):
        if not self.user:
            error = 'You must be logged in to dislike this post.'
            return self.render('login-form.html', error=error)
        post_key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(post_key)
        comments = Comment.all().filter('post =', post_key)
        if self.user.key() == post.author.key():
            error = 'You can not dislike your own post.'
            self.render('permalink.html', post=post, comments=comments,
                        error=error)
        else:
            if post:
                post.dislikes += 1
                post.put()
                return self.redirect('/blog/%s' % post_id)


class CreateComment(BlogHandler):
    def get(self, post_id):
        if not self.user:
            return self.redirect('/login')
        else:
            self.render('addcomment.html')

    def post(self, post_id):
        if not self.user:
            return self.redirect('/login')
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            return self.redirect('/blog')
        content = self.request.get('content')
        author = self.user.key()
        if content:
            c = Comment(parent=key, post=key, content=content, author=author)
            c.put()
            return self.redirect('/blog/%s' % str(post_id))
        else:
            error = 'Please enter a valid comment.'
            self.render('addcomment.html', comment=content, error=error)


class EditComment(BlogHandler):
    def get(self, post_id, comment_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        comment = Comment.get_by_id(int(comment_id), parent=post)

        if not self.user:
            return self.redirect('/login')
        else:
            if comment:
                self.render('editcomment.html', content=comment.content)
            else:
                print "no comment"

    def post(self, post_id, comment_id):
        if not self.user:
            return self.redirect('/blog')
        post_key = db.Key.from_path('Post', int(post_id),
                                    parent=blog_key())
        post = db.get(post_key)
        comment_key = db.Key.from_path('Comment', int(comment_id),
                                       parent=post.key())
        comment = db.get(comment_key)

        if self.user.key().id() == comment.author.key().id():
            content = self.request.get('content')
            author = self.user.key()
            if content:
                comment.content = content
                comment.put()
                return self.redirect('/blog/%s' % str(post_id))
            else:
                error = 'Please enter a valid comment.'
                self.render('editcomment.html', content=comment.content,
                            error=error)


class DeleteComment(BlogHandler):
    def get(self, post_id, comment_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        comment = Comment.get_by_id(int(comment_id), parent=post)
        if not comment:
            self.error(404)
            return
        if self.user:
            self.render("deletecomment.html", post=comment)
        else:
            error = 'You must be logged in to delete this comment.'
            self.render('login-form.html', error=error)

    def post(self, post_id, comment_id):
        if not self.user:
            return self.redirect('/login')
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        comment = Comment.get_by_id(int(comment_id), parent=post)

        if comment and (comment.author.key() == self.user.key()):
            db.delete(comment)
        return self.redirect('/blog/%s' % post_id)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')


def valid_email(email):
    return not email or EMAIL_RE.match(email)


class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username,
                      email=self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Register(Signup):
    def done(self):
        u = User.by_name(self.username)
        if u:
            error = 'That user already exists.'
            self.render('signup-form.html', error_username=error)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            return self.redirect('/blog')


class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            return self.redirect('/blog')
        else:
            error = 'Invalid login'
            self.render('login-form.html', error=error)


class Logout(BlogHandler):
    def get(self):
        self.logout()
        return self.redirect('/blog')


app = webapp2.WSGIApplication([('/', MainPage),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/editpost/([0-9]+)', EditPost),
                               ('/blog/deletepost/([0-9]+)', DeletePost),
                               ('/blog/([0-9]+)/like/', LikePost),
                               ('/blog/([0-9]+)/dislike/', DislikePost),
                               ('/blog/([0-9]+)/newcomment/', CreateComment),
                               ('/blog/([0-9]+)/editcomment/([0-9]+)',
                                EditComment),
                               ('/blog/([0-9]+)/deletecomment/([0-9]+)',
                                DeleteComment),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout)
                               ], debug=True)
