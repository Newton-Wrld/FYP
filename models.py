from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

db = SQLAlchemy()
ph = PasswordHasher()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # descriptive label only — Artist, Producer, Manager, Engineer, Other, Admin

    def set_password(self, password):
        self.password_hash = ph.hash(password)

    def check_password(self, password):
        try:
            return ph.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # "single" or "album"
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    status = db.Column(db.String(20), default="unreleased")  # unreleased / released


class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)       # original owner, never changes
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)     # who uploaded THIS version
    parent_track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=True)  # NULL for original upload

    title = db.Column(db.String(200), nullable=False)
    track_number = db.Column(db.Integer, nullable=True)  # position within an album; NULL for singles

    file_hash = db.Column(db.String(64))
    storage_location = db.Column(db.String(300))

    version_number = db.Column(db.Integer, default=1)
    visibility = db.Column(db.String(10), default="private")  # "public" or "private" — controls default delegate access
    status = db.Column(db.String(20), default="approved")     # pending_review / approved / rejected / unreleased / released

    created_at = db.Column(db.DateTime, server_default=db.func.now())


class TrackPermission(db.Model):
    """Admin-level (Delegate) and limited (Collaborator) access, granted only by the owner."""
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=True)     # per-track grant
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)  # OR catalog-wide grant
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    granted_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)     # must be the owner

    tier = db.Column(db.String(20), nullable=False)  # "delegate" or "collaborator"

    can_distribute = db.Column(db.Boolean, default=False)
    can_approve_revisions = db.Column(db.Boolean, default=False)
    can_set_main_version = db.Column(db.Boolean, default=False)
    can_upload_revision = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def apply_tier_defaults(self):
        """Call after setting .tier to auto-fill the standard flag pattern for that tier."""
        if self.tier == "delegate":
            self.can_distribute = True
            self.can_approve_revisions = True
            self.can_set_main_version = True
            self.can_upload_revision = True
        elif self.tier == "collaborator":
            self.can_distribute = False
            self.can_approve_revisions = False
            self.can_set_main_version = False
            self.can_upload_revision = True


class Distribution(db.Model):
    """A recipient's watermarked copy of a track, with per-share capabilities."""
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # owner or delegate who sent it

    can_stream = db.Column(db.Boolean, default=True)
    can_download = db.Column(db.Boolean, default=False)

    watermark_id = db.Column(db.Integer, db.ForeignKey('watermark.id'), nullable=True)

    created_at = db.Column(db.DateTime, server_default=db.func.now())
    expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="active")  # active / revoked / expired


class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=True)
    action = db.Column(db.String(50))  # LOGIN, DOWNLOAD, DISTRIBUTION, WATERMARK_GENERATED, WATERMARK_EXTRACTED, ACCESS_DENIED, etc.
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())


class Watermark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=False)
    distribution_id = db.Column(db.Integer, db.ForeignKey('distribution.id'), nullable=True)
    watermark_data = db.Column(db.String(200), nullable=False)  # the actual embedded ID string
    algorithm = db.Column(db.String(50), default="DWT-db4")
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class LeakAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=True)  # filled in once matched
    uploaded_file = db.Column(db.String(300))
    watermark_id = db.Column(db.Integer, db.ForeignKey('watermark.id'), nullable=True)
    match_status = db.Column(db.String(20))  # match_found / no_match / corrupted
    analyzed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    analysis_date = db.Column(db.DateTime, server_default=db.func.now())


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # who receives it (the owner)
    message = db.Column(db.String(300), nullable=False)
    related_track_id = db.Column(db.Integer, db.ForeignKey('track.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())