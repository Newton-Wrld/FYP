from flask import Flask, render_template, request, redirect, url_for, flash, abort, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Project, Track, Distribution, Watermark, AccessLog, LeakAnalysis
from watermark import generate_watermarked_copy
import uuid
from datetime import datetime

app = Flask(__name__)
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect(app)
import os
from werkzeug.utils import secure_filename
import hashlib

app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'wav', 'mp3'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music_security.db'
app.config['SECRET_KEY'] = 'change-this-later-to-something-random'  # needed for sessions/flash messages
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # redirects here if a non-logged-in user tries a protected page

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("An account with that email already exists.")
            return redirect(url_for("register"))

        new_user = User(name=name, email=email, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.")
            return redirect(url_for("login"))

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    my_tracks = Track.query.filter_by(owner_id=current_user.id).all()
    shared = (
        db.session.query(Distribution, Track)
        .join(Track, Distribution.track_id == Track.id)
        .filter(Distribution.recipient_id == current_user.id,
                Distribution.status == "active")
        .all()
    )
    return render_template("dashboard.html", my_tracks=my_tracks, shared=shared)

def get_authorized_distribution(dist_id):
    """Return the distribution only if it belongs to the current user and is still valid."""
    dist = Distribution.query.get_or_404(dist_id)

    # Someone else's distribution: pretend it doesn't exist
    if dist.recipient_id != current_user.id:
        db.session.add(AccessLog(user_id=current_user.id, track_id=dist.track_id,
                                 action="ACCESS_DENIED", ip_address=request.remote_addr))
        db.session.commit()
        abort(404)

    if dist.status != "active" or (dist.expires_at and dist.expires_at < datetime.utcnow()):
        abort(403)

    return dist


def serve_distributed_copy(dist, action, as_attachment):
    directory = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], "distributed")
    db.session.add(AccessLog(user_id=current_user.id, track_id=dist.track_id,
                             action=action, ip_address=request.remote_addr))
    db.session.commit()
    return send_from_directory(directory, f"dist_{dist.id}.wav", as_attachment=as_attachment)


@app.route("/distribution/<int:dist_id>/stream")
@login_required
def stream(dist_id):
    dist = get_authorized_distribution(dist_id)
    if not dist.can_stream:
        abort(403)
    return serve_distributed_copy(dist, "STREAM", as_attachment=False)


@app.route("/distribution/<int:dist_id>/download")
@login_required
def download(dist_id):
    dist = get_authorized_distribution(dist_id)
    if not dist.can_download:
        abort(403)
    return serve_distributed_copy(dist, "DOWNLOAD", as_attachment=True)

@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title")
        file = request.files.get("audio_file")

        if not file or file.filename == "":
            flash("Please choose an audio file.")
            return redirect(url_for("upload"))

        if not allowed_file(file.filename):
            flash("Only WAV or MP3 files are allowed.")
            return redirect(url_for("upload"))

        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(save_path)

        # Validate that this is genuinely readable audio, not just correctly named
        from watermark import load_audio_any_format
        try:
            load_audio_any_format(save_path)
        except Exception:
            os.remove(save_path)  # clean up the invalid file
            flash("The uploaded file is not valid audio. Please upload a genuine WAV or MP3 file.")
            return redirect(url_for("upload"))

        # Compute a hash of the file for integrity tracking (Section 13 of the proposal)
        with open(save_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Auto-create a "single" project to hold this track
        new_project = Project(owner_id=current_user.id, title=title, type="single")
        db.session.add(new_project)
        db.session.commit()  # commit now so new_project.id is available

        new_track = Track(
            project_id=new_project.id,
            owner_id=current_user.id,
            uploaded_by=current_user.id,
            title=title,
            file_hash=file_hash,
            storage_location=save_path,
            version_number=1,
            visibility="private",
            status="approved"
        )
        db.session.add(new_track)
        db.session.commit()

        flash(f"'{title}' uploaded successfully.")
        return redirect(url_for("dashboard"))

    return render_template("upload.html")

@app.route("/track/<int:track_id>/distribute", methods=["GET", "POST"])
@login_required
def distribute(track_id):
    track = Track.query.get_or_404(track_id)

    # For now: only the owner can distribute (delegate support comes later)
    if track.owner_id != current_user.id:
        flash("You don't have permission to distribute this track.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        recipient_email = request.form.get("recipient_email")
        can_stream = bool(request.form.get("can_stream"))
        can_download = bool(request.form.get("can_download"))

        recipient = User.query.filter_by(email=recipient_email).first()
        if not recipient:
            flash("No account found with that email. The recipient must register first.")
            return redirect(url_for("distribute", track_id=track_id))

        # Create the Distribution record first so we have its ID
        new_dist = Distribution(
            track_id=track.id,
            recipient_id=recipient.id,
            sent_by=current_user.id,
            can_stream=can_stream,
            can_download=can_download,
            status="active"
        )
        db.session.add(new_dist)
        db.session.commit()  # commit to get new_dist.id

        # Generate a unique watermark tied to this exact distribution
        watermark_text = uuid.uuid4().hex[:16]  # fixed 16-character watermark, always

        source_path = track.storage_location
        output_filename = f"dist_{new_dist.id}.wav"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], "distributed", output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        generate_watermarked_copy(source_path, watermark_text, output_path)

        # Record the watermark
        new_watermark = Watermark(
            track_id=track.id,
            distribution_id=new_dist.id,
            watermark_data=watermark_text,
            algorithm="DWT-db4"
        )
        db.session.add(new_watermark)
        db.session.commit()

        # Link the watermark back to the distribution, and store the protected file path
        new_dist.watermark_id = new_watermark.id
        db.session.commit()

        # Log the event
        log = AccessLog(
            user_id=current_user.id,
            track_id=track.id,
            action="DISTRIBUTION",
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

        flash(f"'{track.title}' distributed to {recipient.name} successfully.")
        return redirect(url_for("dashboard"))

    return render_template("distribute.html", track=track) 

@app.route("/leak-analysis", methods=["GET", "POST"])
@login_required
def leak_analysis():
    result = None

    if request.method == "POST":
        file = request.files.get("suspect_file")
        if not file or file.filename == "":
            flash("Please choose a file to analyze.")
            return redirect(url_for("leak_analysis"))

        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], "leak_checks", filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        file.save(save_path)

        from watermark import load_audio_any_format, extract_watermark

        try:
            audio, sr = load_audio_any_format(save_path)
            extracted_id = extract_watermark(audio, 16)
            match = Watermark.query.filter_by(watermark_data=extracted_id).first()
        except Exception as e:
            flash("The uploaded file could not be processed as valid audio.")
            return redirect(url_for("leak_analysis"))

        log_entry = LeakAnalysis(
            track_id=match.track_id if match else None,
            uploaded_file=save_path,
            watermark_id=match.id if match else None,
            match_status="match_found" if match else "no_match",
            analyzed_by=current_user.id
        )
        db.session.add(log_entry)
        db.session.commit()

        if match:
            track = Track.query.get(match.track_id)
            distribution = Distribution.query.get(match.distribution_id)

            if track.owner_id == current_user.id:
                result = {
                    "status": "MATCH FOUND",
                    "track_id": match.track_id,
                    "distribution_id": match.distribution_id,
                    "recipient_name": User.query.get(distribution.recipient_id).name,
                    "recipient_email": User.query.get(distribution.recipient_id).email,
                    "distributed_on": distribution.created_at
                }
            else:
                result = {
                    "status": "MATCH FOUND — this file is watermarked and traceable, but you don't have permission to view investigation details. Contact the track owner."
                }
        else:
            result = {"status": "NO MATCH — watermark not recognized or file was not watermarked by this system."}

    return render_template("leak_analysis.html", result=result)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)

  