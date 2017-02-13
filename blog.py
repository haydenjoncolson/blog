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
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

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


##### user stuff
def make_salt(length = 5):
    return ''.join(random.choice(letters) for x in xrange(length))

def make_pw_hash(name, pw, salt = None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)

def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)

def users_key(group = 'default'):
    return db.Key.from_path('users', group)

class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent = users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


##### blog stuff

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)



class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)
    #author = db.StringProperty(required=False)
    author = db.ReferenceProperty(User)
    likes = db.IntegerProperty(default=0)



    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)


class Comment(db.Model):
    post = db.ReferenceProperty(Post)
    comment = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    author =  db.ReferenceProperty(User)
    # def render(self):
    #     #return render_str("post.html", c = self)

class BlogFront(BlogHandler):
    def get(self):
        posts = greetings = Post.all().order('-created')
        # comments = Comment.all().order('-created')
        self.render('front.html', posts = posts)

class PostPage(BlogHandler):
    def get(self, post_id):
        post_key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(post_key)
        if not post:
            self.error(404)
            return
        print post.content
        comments = Comment.all().filter('post =', post_key)

        self.render("permalink.html", post = post, comments = comments)

class NewPost(BlogHandler):
    def get(self):
        if self.user:
            author = self.user.key()
            self.render("newpost.html", author=author)
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            self.redirect('/blog')

        subject = self.request.get('subject')
        content = self.request.get('content')
        author = self.user.key()

        if subject and content:
            p = Post(parent = blog_key(), subject = subject, content = content, author = author)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error, author= author)

class EditPost(BlogHandler):
    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if post:
            if self.user:
                if post.author.key().id() != self.user.key().id():
                    self.redirect('/blog/%s' % str(post.key().id()))
                else:
                    self.render("editpost.html", subject=post.subject, content=post.content)
            else:
                error = 'You must be logged in to edit post.'
                self.render('login-form.html', error=error)
        else:
            self.write("post not found")


    def post(self, post_id):
        if not self.user:
            self.redirect('/blog')

        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        subject = self.request.get('subject')
        content = self.request.get('content')


        if subject and content:
            post.subject = subject
            post.content = content
            post.put()
            self.redirect('/blog')
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
            self.redirect('/login')
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if post and (post.author.key() == self.user.key()):
            db.delete(post)
        self.redirect('/blog')




class CreateComment(BlogHandler):
    def get(self, post_id):
        if not self.user:
            self.redirect('/login')
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
            c = Comment(parent=key, post=key, comment=content, author=author)
            c.put()
            self.redirect('/blog/%s' % str(post_id))
        else:
            error = 'Please enter a valid comment.'
            self.render('addcomment.html', content=content, error=error)

class EditComment(BlogHandler):
    def get(self, post_id, comment_id):
        #comment_key = db.Key.from_path('Comment', int(comment_id), parent=blog_key())
        #comment = Comment.get(comment_key)
        #print str(comment_key)
        #print comment
        #print comment_key.id()
        print comment_id
        comment = Comment.get_by_id(int(comment_id))
        print comment.comment
        if not self.user:
            return self.redirect('/login')
        else:
            if comment:
                self.render('editcomment.html', content=comment.comment)
            else:
                #self.redirect('/blog/%s'%str(post_id))
                print "no comment"

    def post(self, post_id, comment_id):
        if not self.user:
            self.redirect('/blog')
        comment_key = db.Key.from_path('Comment', int(comment_id), parent=blog_key())
        comment = db.get(comment_key)

        if self.user.key().id() == comment.author.key().id():
            content = self.request.get('content')
            author = self.user.key()
            if content:
                c = Comment(parent=key, content=content, author=author)
                c.put()
                self.redirect('/blog/%s' % str(post_id))
            else:
                error = 'Please enter a valid comment.'
                self.render('editcomment.html', content=comment.content, error=error)

class Like(db.Model):
    author = db.ReferenceProperty(User)
    post = db.ReferenceProperty(Post)
    likes = db.IntegerProperty()

USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
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

        params = dict(username = self.username,
                      email = self.email)

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
        #make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            error = 'That user already exists.'
            self.render('signup-form.html', error_username = error)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/blog')

class Login(BlogHandler):
    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            error = 'Invalid login'
            self.render('login-form.html', error = error)

class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/blog')


app = webapp2.WSGIApplication([('/', MainPage),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/editpost/([0-9]+)', EditPost),
                               ('/blog/deletepost/([0-9]+)', DeletePost),
                              # ('/blog/likepost/([0-9]+)', LikePost),
                              # ('/blog/unlikepost/([0-9]+)', UnlikePost),
                               ('/blog/([0-9]+)/newcomment/', CreateComment),
                               ('/blog/([0-9]+)/editcomment/([0-9]+)', EditComment),
                              # ('/blog/([0-9]+)/deletecomment/([0-9]+)', DeleteComment),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout)
                               ], debug=True)
