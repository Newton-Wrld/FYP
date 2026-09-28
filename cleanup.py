from app import app, db
from models import Track, Project

with app.app_context():
    track = Track.query.get(2)
    if track:
        print("Found:", track.id, track.title, track.project_id)
        project_id = track.project_id

        db.session.delete(track)
        db.session.commit()
        print("Track deleted")

        project = Project.query.get(project_id)
        if project:
            db.session.delete(project)
            db.session.commit()
            print("Project deleted")
    else:
        print("Track 2 not found")

    print("\nRemaining tracks:")
    for t in Track.query.all():
        print(t.id, t.title, t.storage_location)