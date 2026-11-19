import os
from datetime import datetime
from functools import wraps
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from flask import (Flask, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

def db():
    return mysql.connector.connect(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.getenv("DB_NAME", "college_events"),
    )

def query(sql, params=(), one=False, commit=False):
    conn = db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        result = cur.fetchone() if one else cur.fetchall()
        if commit:
            conn.commit()
        return result
    finally:
        cur.close()
        conn.close()

def current_user():
    if "user_id" not in session:
        return None
    return query("SELECT id,name,email,role FROM users WHERE id=%s",
                 (session["user_id"],), one=True)

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if user["role"] not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.context_processor
def inject_user():
    user = current_user()
    unread = 0
    if user:
        row = query("SELECT COUNT(*) AS n FROM notifications WHERE user_id=%s AND is_read=0",
                    (user["id"],), one=True)
        unread = row["n"]
    return {"logged_user": user, "unread_notifications": unread}

@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    club = request.args.get("club", "").strip()
    date = request.args.get("date", "").strip()
    sql = """SELECT e.*, c.name AS club_name,
             (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registrations_count
             FROM events e JOIN clubs c ON c.id=e.club_id
             WHERE e.status='upcoming' AND e.event_date >= NOW()"""
    params = []
    if search:
        sql += " AND (e.title LIKE %s OR e.description LIKE %s OR c.name LIKE %s)"
        params += [f"%{search}%"] * 3
    if category:
        sql += " AND e.category=%s"
        params.append(category)
    if club:
        sql += " AND c.id=%s"
        params.append(club)
    if date:
        sql += " AND DATE(e.event_date)=%s"
        params.append(date)
    sql += " ORDER BY e.event_date ASC"
    events = query(sql, tuple(params))
    clubs = query("SELECT id,name FROM clubs WHERE approved=1 ORDER BY name")
    categories = query("SELECT DISTINCT category FROM events ORDER BY category")
    return render_template("index.html", events=events, clubs=clubs,
                           categories=categories, filters={
                               "q": search, "category": category,
                               "club": club, "date": date
                           })

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")
        club_name = request.form.get("club_name", "").strip()
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email and a password of at least 8 characters.", "danger")
            return render_template("signup.html")
        if role not in ("student", "organizer"):
            role = "student"
        try:
            query("INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,%s)",
                  (name, email, generate_password_hash(password), role), commit=True)
            user = query("SELECT id,name,role FROM users WHERE email=%s", (email,), one=True)
            if role == "organizer":
                if not club_name:
                    club_name = name + "'s Club"
                query("INSERT INTO clubs(name,description,organizer_id) VALUES(%s,%s,%s)",
                      (club_name, "College club profile. Update this description later.", user["id"]),
                      commit=True)
            session["user_id"] = user["id"]
            flash("Account created successfully. Welcome!", "success")
            return redirect(url_for("dashboard"))
        except mysql.connector.IntegrityError:
            flash("That email address is already registered.", "danger")
        except mysql.connector.Error as exc:
            flash(f"Database error: {exc}", "danger")
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query("SELECT * FROM users WHERE email=%s", (email,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("You are now logged in.", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user["role"] == "organizer":
        events = query("""SELECT e.*,
            (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registrations_count
            FROM events e WHERE e.organizer_id=%s ORDER BY e.event_date DESC""",
            (user["id"],))
        return render_template("organizer_dashboard.html", events=events)
    if user["role"] == "admin":
        stats = {
            "users": query("SELECT COUNT(*) n FROM users", one=True)["n"],
            "events": query("SELECT COUNT(*) n FROM events", one=True)["n"],
            "clubs": query("SELECT COUNT(*) n FROM clubs", one=True)["n"],
        }
        users = query("SELECT id,name,email,role,created_at FROM users ORDER BY created_at DESC")
        return render_template("admin_dashboard.html", stats=stats, users=users)
    registrations = query("""SELECT e.*, c.name AS club_name, r.registered_at
        FROM registrations r JOIN events e ON e.id=r.event_id
        JOIN clubs c ON c.id=e.club_id WHERE r.student_id=%s
        ORDER BY e.event_date ASC""", (user["id"],))
    notifications = query("""SELECT * FROM notifications WHERE user_id=%s
        ORDER BY created_at DESC LIMIT 10""", (user["id"],))
    return render_template("student_dashboard.html",
                           registrations=registrations, notifications=notifications)

@app.route("/event/<int:event_id>")
def event_detail(event_id):
    event = query("""SELECT e.*,c.name AS club_name,u.name AS organizer_name,
        (SELECT COUNT(*) FROM registrations r WHERE r.event_id=e.id) AS registrations_count,
        (SELECT COUNT(*) FROM likes l WHERE l.event_id=e.id) AS likes_count
        FROM events e JOIN clubs c ON c.id=e.club_id
        JOIN users u ON u.id=e.organizer_id WHERE e.id=%s""",
        (event_id,), one=True)
    if not event:
        flash("Event not found.", "danger")
        return redirect(url_for("index"))
    comments = query("""SELECT c.*,u.name AS user_name FROM comments c
        JOIN users u ON u.id=c.user_id WHERE c.event_id=%s ORDER BY c.created_at DESC""",
        (event_id,))
    registered = False
    liked = False
    if current_user():
        registered = bool(query("SELECT id FROM registrations WHERE event_id=%s AND student_id=%s",
                                (event_id, current_user()["id"]), one=True))
        liked = bool(query("SELECT id FROM likes WHERE event_id=%s AND user_id=%s",
                           (event_id, current_user()["id"]), one=True))
    rating = query("SELECT AVG(rating) AS average FROM ratings WHERE event_id=%s",
                   (event_id,), one=True)["average"]
    return render_template("event_detail.html", event=event, comments=comments,
                           registered=registered, liked=liked, average_rating=rating)

@app.route("/event/create", methods=["GET", "POST"])
@roles_required("organizer", "admin")
def create_event():
    user = current_user()
    clubs = query("SELECT * FROM clubs WHERE organizer_id=%s OR %s='admin'",
                  (user["id"], user["role"]))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        date_value = request.form.get("event_date", "").strip()
        venue = request.form.get("venue", "").strip()
        club_id = request.form.get("club_id", "").strip()
        registration_url = request.form.get("registration_url", "").strip()
        if not all([title, description, category, date_value, venue, club_id]):
            flash("Please complete all required fields.", "danger")
            return render_template("create_event.html", clubs=clubs, event=None)
        owned = query("SELECT id FROM clubs WHERE id=%s AND (organizer_id=%s OR %s='admin')",
                      (club_id, user["id"], user["role"]), one=True)
        if not owned:
            flash("You cannot publish events for that club.", "danger")
            return redirect(url_for("create_event"))
        poster = request.files.get("poster")
        filename = None
        if poster and poster.filename:
            if not allowed_file(poster.filename):
                flash("Poster must be PNG, JPG, JPEG, WEBP or GIF.", "danger")
                return render_template("create_event.html", clubs=clubs, event=None)
            filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(poster.filename)}"
            poster.save(UPLOAD_DIR / filename)
        query("""INSERT INTO events(club_id,organizer_id,title,category,description,
            event_date,venue,registration_url,poster_filename)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (club_id, user["id"], title, category, description, date_value,
             venue, registration_url or None, filename), commit=True)
        flash("Your event has been published.", "success")
        return redirect(url_for("dashboard"))
    return render_template("create_event.html", clubs=clubs, event=None)

@app.route("/event/<int:event_id>/edit", methods=["GET", "POST"])
@roles_required("organizer", "admin")
def edit_event(event_id):
    user = current_user()
    event = query("SELECT * FROM events WHERE id=%s", (event_id,), one=True)
    if not event or (user["role"] != "admin" and event["organizer_id"] != user["id"]):
        flash("Event not found or you do not have permission.", "danger")
        return redirect(url_for("dashboard"))
    clubs = query("SELECT * FROM clubs WHERE organizer_id=%s OR %s='admin'",
                  (user["id"], user["role"]))
    if request.method == "POST":
        query("""UPDATE events SET title=%s,category=%s,description=%s,event_date=%s,
            venue=%s,registration_url=%s WHERE id=%s""",
            (request.form["title"].strip(), request.form["category"].strip(),
             request.form["description"].strip(), request.form["event_date"],
             request.form["venue"].strip(), request.form.get("registration_url") or None,
             event_id), commit=True)
        poster = request.files.get("poster")
        if poster and poster.filename and allowed_file(poster.filename):
            filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(poster.filename)}"
            poster.save(UPLOAD_DIR / filename)
            query("UPDATE events SET poster_filename=%s WHERE id=%s",
                  (filename, event_id), commit=True)
        flash("Event updated.", "success")
        return redirect(url_for("dashboard"))
    return render_template("create_event.html", clubs=clubs, event=event)

@app.route("/event/<int:event_id>/delete", methods=["POST"])
@roles_required("organizer", "admin")
def delete_event(event_id):
    user = current_user()
    event = query("SELECT * FROM events WHERE id=%s", (event_id,), one=True)
    if event and (user["role"] == "admin" or event["organizer_id"] == user["id"]):
        query("DELETE FROM events WHERE id=%s", (event_id,), commit=True)
        flash("Event deleted.", "success")
    else:
        flash("You cannot delete that event.", "danger")
    return redirect(url_for("dashboard"))

@app.route("/event/<int:event_id>/register", methods=["POST"])
@roles_required("student")
def register_event(event_id):
    user = current_user()
    event = query("SELECT id,title FROM events WHERE id=%s AND status='upcoming'",
                  (event_id,), one=True)
    if not event:
        flash("This event is not available for registration.", "danger")
        return redirect(url_for("index"))
    try:
        query("INSERT INTO registrations(event_id,student_id) VALUES(%s,%s)",
              (event_id, user["id"]), commit=True)
        query("INSERT INTO notifications(user_id,message,link) VALUES(%s,%s,%s)",
              (user["id"], f"Registration confirmed for {event['title']}.",
               url_for("event_detail", event_id=event_id)), commit=True)
        flash("Registration successful! Confirmation saved in your dashboard.", "success")
    except mysql.connector.IntegrityError:
        flash("You have already registered for this event.", "info")
    return redirect(url_for("event_detail", event_id=event_id))

@app.route("/event/<int:event_id>/comment", methods=["POST"])
@login_required
def add_comment(event_id):
    body = request.form.get("body", "").strip()
    if body:
        query("INSERT INTO comments(event_id,user_id,body) VALUES(%s,%s,%s)",
              (event_id, current_user()["id"], body), commit=True)
        event = query("SELECT organizer_id,title FROM events WHERE id=%s", (event_id,), one=True)
        if event and event["organizer_id"] != current_user()["id"]:
            query("INSERT INTO notifications(user_id,message,link) VALUES(%s,%s,%s)",
                  (event["organizer_id"], f"New comment on {event['title']}.",
                   url_for("event_detail", event_id=event_id)), commit=True)
        flash("Comment added.", "success")
    return redirect(url_for("event_detail", event_id=event_id))

@app.route("/event/<int:event_id>/like", methods=["POST"])
@login_required
def like_event(event_id):
    user_id = current_user()["id"]
    existing = query("SELECT id FROM likes WHERE event_id=%s AND user_id=%s",
                     (event_id, user_id), one=True)
    if existing:
        query("DELETE FROM likes WHERE id=%s", (existing["id"],), commit=True)
    else:
        query("INSERT INTO likes(event_id,user_id) VALUES(%s,%s)",
              (event_id, user_id), commit=True)
    return redirect(url_for("event_detail", event_id=event_id))

@app.route("/event/<int:event_id>/rate", methods=["POST"])
@roles_required("student")
def rate_event(event_id):
    rating = request.form.get("rating", type=int)
    review = request.form.get("review", "").strip()
    if rating and 1 <= rating <= 5:
        query("""INSERT INTO ratings(event_id,user_id,rating,review) VALUES(%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE rating=VALUES(rating),review=VALUES(review)""",
            (event_id, current_user()["id"], rating, review), commit=True)
        flash("Thanks for rating this event.", "success")
    return redirect(url_for("event_detail", event_id=event_id))

@app.route("/notifications")
@login_required
def notifications():
    user = current_user()
    items = query("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC",
                  (user["id"],))
    query("UPDATE notifications SET is_read=1 WHERE user_id=%s", (user["id"],), commit=True)
    return render_template("notifications.html", items=items)

@app.route("/club/<int:club_id>")
def club_page(club_id):
    club = query("SELECT c.*,u.name AS organizer_name FROM clubs c JOIN users u ON u.id=c.organizer_id WHERE c.id=%s",
                 (club_id,), one=True)
    if not club:
        flash("Club not found.", "danger")
        return redirect(url_for("index"))
    events = query("SELECT * FROM events WHERE club_id=%s ORDER BY event_date DESC", (club_id,))
    return render_template("club.html", club=club, events=events)

@app.route("/admin/user/<int:user_id>/role", methods=["POST"])
@roles_required("admin")
def change_role(user_id):
    role = request.form.get("role")
    if role in ("student", "organizer", "admin"):
        query("UPDATE users SET role=%s WHERE id=%s", (role, user_id), commit=True)
        flash("User role updated.", "success")
    return redirect(url_for("dashboard"))

@app.errorhandler(413)
def too_large(_error):
    flash("Upload is too large. Maximum file size is 5 MB.", "danger")
    return redirect(request.referrer or url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
