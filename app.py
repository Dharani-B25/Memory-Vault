
import os
import re
from datetime import datetime, date, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
    Response,
    render_template_string
)

from flask_login import (
    current_user,
    login_user,
    logout_user,
    login_required
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from sqlalchemy import or_

from config import Config
from extensions import db, login_manager, csrf
from models import User, Task, Note, NoteVersion, LearningLog


USER_ROLES = {
    "student": "Student",
    "professional": "Working Professional",
    "entrepreneur": "Entrepreneur",
}


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # ---------------- HOME PAGE ----------------

    @app.route("/")
    def home():
        return render_template("index.html")

    # ---------------- AUTH PAGE ----------------

    @app.route("/auth")
    def auth():
        role_key = request.args.get("role", "").lower()

        if role_key not in USER_ROLES:
            return redirect(url_for("home"))

        return render_template(
            "auth.html",
            role=USER_ROLES[role_key],
            role_key=role_key
        )

    # ---------------- REGISTER ----------------

    @app.route("/register", methods=["POST"])
    def register():
        role_key = request.args.get("role", "").lower()

        if role_key not in USER_ROLES:
            flash("Please select a valid category.", "error")
            return redirect(url_for("home"))

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all registration fields.", "error")
            return redirect(url_for("auth", role=role_key))

        if (
            len(name) > 100
            or len(email) > 255
            or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        ):
            flash("Please enter a valid name and email.", "error")
            return redirect(url_for("auth", role=role_key))

        if len(password) < 8:
            flash(
                "Password must be at least 8 characters long.",
                "error"
            )
            return redirect(url_for("auth", role=role_key))

        existing_user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if existing_user:
            flash(
                "An account with this email already exists.",
                "error"
            )
            return redirect(url_for("auth", role=role_key))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role_key
        )

        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Account created successfully!", "success")

        return redirect(url_for("dashboard"))

    # ---------------- LOGIN ----------------

    @app.route("/login", methods=["POST"])
    def login():
        role_key = request.args.get("role", "").lower()

        if role_key not in USER_ROLES:
            flash("Please select a valid category.", "error")
            return redirect(url_for("home"))

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if (
            user is None
            or not check_password_hash(user.password_hash, password)
            or user.role != role_key
        ):
            flash(
                "Email, password, or selected category is incorrect.",
                "error"
            )
            return redirect(url_for("auth", role=role_key))

        login_user(user)
        flash("Welcome back!", "success")

        return redirect(url_for("dashboard"))

    # ---------------- DASHBOARD ----------------

    @app.route("/dashboard")
    @login_required
    def dashboard():
        status_filter = request.args.get("status", "All")
        priority_filter = request.args.get("priority", "All")

        if status_filter not in ["All", "Pending", "Completed"]:
            status_filter = "All"

        if priority_filter not in ["All", "Low", "Medium", "High"]:
            priority_filter = "All"

        # Fetch all tasks for the current user
        all_tasks = db.session.scalars(
            db.select(Task)
            .where(Task.user_id == current_user.id)
            .order_by(Task.created_at.desc())
        ).all()

        total_tasks = len(all_tasks)

        completed_tasks = sum(
            1 for task in all_tasks
            if task.status == "Completed"
        )

        pending_tasks = total_tasks - completed_tasks
        notes_query = db.select(Note).where(Note.user_id == current_user.id, Note.is_archived.is_(False))
        user_notes = db.session.scalars(notes_query).all()
        weekly_logs = db.session.scalars(db.select(LearningLog).where(
            LearningLog.user_id == current_user.id,
            LearningLog.log_date >= date.today() - timedelta(days=6)
        ).order_by(LearningLog.log_date.desc())).all()
        week_start = date.today() - timedelta(days=date.today().weekday())
        weekly_completed = db.session.scalars(db.select(Task).where(
            Task.user_id == current_user.id,
            Task.completed_at >= datetime.combine(week_start, datetime.min.time())
        )).all()
        today = date.today()

        overdue_tasks = sum(
            1 for task in all_tasks
            if task.status == "Pending"
            and task.due_date is not None
            and task.due_date < today
        )

        # Filter tasks
        query = db.select(Task).where(
            Task.user_id == current_user.id
        )

        if status_filter != "All":
            query = query.where(Task.status == status_filter)

        if priority_filter != "All":
            query = query.where(Task.priority == priority_filter)

        tasks = db.session.scalars(
            query.order_by(Task.created_at.desc())
        ).all()

        return render_template(
            "dashboard.html",
            role=USER_ROLES.get(current_user.role, "User"),
            tasks=tasks,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            pending_tasks=pending_tasks,
            overdue_tasks=overdue_tasks,
            today=today,
            status_filter=status_filter,
            priority_filter=priority_filter,
            total_notes=len(user_notes), notes_by_category={c: sum(1 for n in user_notes if n.category == c) for c in {n.category for n in user_notes}},
            recent_notes=sorted(user_notes, key=lambda n: n.updated_at or datetime.min, reverse=True)[:4],
            completion_percent=round(completed_tasks * 100 / total_tasks) if total_tasks else 0,
            weekly_logs=weekly_logs,
            weekly_completed_count=len(weekly_completed)
        )

    # ---------------- ADD TASK ----------------

    @app.route("/tasks/add", methods=["POST"])
    @login_required
    def add_task():
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date_text = request.form.get("due_date", "").strip()
        priority = request.form.get("priority", "Medium")

        if not title:
            flash("Task title is required.", "error")
            return redirect(url_for("dashboard"))

        if len(title) > 150:
            flash("Task title must be 150 characters or less.", "error")
            return redirect(url_for("dashboard"))

        if len(description) > 5000:
            flash("Task description must be 5,000 characters or less.", "error")
            return redirect(url_for("dashboard"))

        if priority not in ["Low", "Medium", "High"]:
            priority = "Medium"

        parsed_due_date = None

        if due_date_text:
            try:
                parsed_due_date = datetime.strptime(
                    due_date_text, "%Y-%m-%d"
                ).date()
            except ValueError:
                flash("Please enter a valid due date.", "error")
                return redirect(url_for("dashboard"))

        task = Task(
            title=title,
            description=description,
            due_date=parsed_due_date,
            priority=priority,
            status="Pending",
            user_id=current_user.id
        )

        db.session.add(task)
        db.session.commit()

        flash("Task added successfully!", "success")
        return redirect(url_for("dashboard"))

    # ---------------- EDIT TASK ----------------

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_task(task_id):
        task = db.session.scalar(
            db.select(Task).where(
                Task.id == task_id,
                Task.user_id == current_user.id
            )
        )

        if task is None:
            abort(404)

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date_text = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "Medium")

            if not title:
                flash("Task title is required.", "error")
                return redirect(
                    url_for("edit_task", task_id=task.id)
                )

            if len(title) > 150:
                flash("Title must be 150 characters or less.", "error")
                return redirect(
                    url_for("edit_task", task_id=task.id)
                )

            if len(description) > 5000:
                flash("Description must be 5,000 characters or less.", "error")
                return redirect(url_for("edit_task", task_id=task.id))

            if priority not in ["Low", "Medium", "High"]:
                priority = "Medium"

            parsed_due_date = None

            if due_date_text:
                try:
                    parsed_due_date = datetime.strptime(
                        due_date_text, "%Y-%m-%d"
                    ).date()
                except ValueError:
                    flash("Please enter a valid due date.", "error")
                    return redirect(
                        url_for("edit_task", task_id=task.id)
                    )

            task.title = title
            task.description = description
            task.due_date = parsed_due_date
            task.priority = priority

            db.session.commit()

            flash("Task updated successfully!", "success")
            return redirect(url_for("dashboard"))

        return render_template("edit_task.html", task=task)

    # ---------------- COMPLETE / PENDING TASK ----------------

    @app.route("/tasks/<int:task_id>/complete", methods=["POST"])
    @login_required
    def complete_task(task_id):
        task = db.session.scalar(
            db.select(Task).where(
                Task.id == task_id,
                Task.user_id == current_user.id
            )
        )

        if task is None:
            abort(404)

        if task.status == "Completed":
            task.status = "Pending"
            task.completed_at = None
        else:
            task.status = "Completed"
            task.completed_at = datetime.utcnow()

        db.session.commit()

        flash("Task status updated!", "success")
        return redirect(url_for("dashboard"))

    # ---------------- DELETE TASK ----------------

    @app.route("/tasks/<int:task_id>/delete", methods=["POST"])
    @login_required
    def delete_task(task_id):
        task = db.session.scalar(
            db.select(Task).where(
                Task.id == task_id,
                Task.user_id == current_user.id
            )
        )

        if task is None:
            abort(404)

        db.session.delete(task)
        db.session.commit()

        flash("Task deleted successfully!", "success")
        return redirect(url_for("dashboard"))

    # ---------------- MY NOTES + SEARCH ----------------

    @app.route("/notes", methods=["GET"])
    @login_required
    def notes():
        search_query = request.args.get("q", "").strip()
        category_filter = request.args.get("category", "").strip()
        tag_filter = request.args.get("tag", "").strip()
        date_filter = request.args.get("date", "").strip()
        show_archived = request.args.get("archived") == "1"

        query = db.select(Note).where(
            Note.user_id == current_user.id,
            Note.is_archived.is_(show_archived)
        )

        if category_filter:
            query = query.where(Note.category == category_filter)
        if tag_filter:
            query = query.where(Note.tags.ilike(f"%{tag_filter}%"))
        type_filter = request.args.get("type", "").strip()
        revision_mode = request.args.get("revision") == "1"
        if type_filter in ["Note", "Code Snippet"]:
            query = query.where(Note.note_type == type_filter)
        if revision_mode:
            query = query.where(Note.review_date.is_not(None), Note.review_date <= date.today(), Note.is_archived.is_(False))
        if date_filter:
            try:
                filter_date = datetime.strptime(date_filter, "%Y-%m-%d").date()
                query = query.where(db.func.date(Note.created_at) == filter_date.isoformat())
            except ValueError:
                date_filter = ""

        if search_query:
            keyword = f"%{search_query}%"

            query = query.where(
                or_(
                    Note.title.ilike(keyword),
                    Note.content.ilike(keyword),
                    Note.category.ilike(keyword),
                    Note.tags.ilike(keyword)
                )
            )

        saved_notes = db.session.scalars(
            query.order_by(Note.updated_at.desc())
        ).all()
        all_user_notes = db.session.scalars(db.select(Note).where(Note.user_id == current_user.id)).all()
        related_notes = {}
        for note in saved_notes:
            titles = {part.strip().casefold() for part in (note.related_titles or "").split(",") if part.strip()}
            related_notes[note.id] = [other for other in all_user_notes if other.id != note.id and other.title.casefold() in titles]

        return render_template(
            "notes.html",
            notes=saved_notes,
            search_query=search_query, category_filter=category_filter,
            tag_filter=tag_filter, date_filter=date_filter, show_archived=show_archived,
            type_filter=type_filter, revision_mode=revision_mode,
            related_notes=related_notes,
            today=date.today(),
            due_reviews=db.session.scalars(db.select(Note).where(Note.user_id == current_user.id, Note.is_archived.is_(False), Note.review_date.is_not(None), Note.review_date <= date.today()).order_by(Note.review_date)).all(),
            categories=db.session.scalars(db.select(Note.category).where(Note.user_id == current_user.id).distinct()).all()
        )

    # ---------------- ADD NOTE ----------------

    @app.route("/notes/add", methods=["POST"])
    @login_required
    def add_note():
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        category = request.form.get("category", "General").strip()
        tags = request.form.get("tags", "").strip()
        related_titles = request.form.get("related_titles", "").strip()
        note_type = request.form.get("note_type", "Note")

        if not title or not content:
            flash("Title and content are required.", "error")
            return redirect(url_for("notes"))

        if len(title) > 200:
            flash("Title must be 200 characters or less.", "error")
            return redirect(url_for("notes"))

        if len(category) > 100 or len(tags) > 300 or len(related_titles) > 500 or len(content) > 100000:
            flash("Category, tags, related titles, or content exceed the allowed length.", "error")
            return redirect(url_for("notes"))

        if note_type not in ["Note", "Code Snippet"]:
            note_type = "Note"

        new_note = Note(
            title=title,
            content=content,
            category=category or "General",
            tags=tags,
            note_type=note_type,
            related_titles=related_titles[:500],
            user_id=current_user.id
        )

        db.session.add(new_note)
        db.session.commit()

        flash("Note saved successfully!", "success")
        return redirect(url_for("notes"))

    @app.route("/notes/<int:note_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_note(note_id):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == current_user.id))
        if note is None: abort(404)
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            content = request.form.get("content", "").strip()
            category = request.form.get("category", "General").strip() or "General"
            tags = request.form.get("tags", "").strip()
            related_titles = request.form.get("related_titles", "").strip()
            review_date_text = request.form.get("review_date", "").strip()
            note_type = request.form.get("note_type", "Note")
            try: review_date = datetime.strptime(review_date_text, "%Y-%m-%d").date() if review_date_text else None
            except ValueError: review_date = date.min
            if not title or not content or len(title) > 200 or len(category) > 100 or len(tags) > 300 or len(content) > 100000 or len(related_titles) > 500 or review_date == date.min:
                flash("Enter a title and content; keep category and tags within the limits.", "error")
                return redirect(url_for("edit_note", note_id=note.id))
            db.session.add(NoteVersion(note_id=note.id, title=note.title, content=note.content, category=note.category, tags=note.tags, note_type=note.note_type, related_titles=note.related_titles, review_date=note.review_date))
            note.title, note.content, note.category, note.tags = title, content, category, tags
            note.note_type = note_type if note_type in ["Note", "Code Snippet"] else "Note"
            note.related_titles = related_titles[:500]
            note.review_date = review_date
            db.session.commit()
            flash("Note updated. Previous content is saved in version history.", "success")
            return redirect(url_for("notes"))
        versions = db.session.scalars(db.select(NoteVersion).where(NoteVersion.note_id == note.id).order_by(NoteVersion.created_at.desc())).all()
        return render_template("edit_note.html", note=note, versions=versions)

    @app.route("/notes/<int:note_id>/delete", methods=["POST"])
    @login_required
    def delete_note(note_id):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == current_user.id))
        if note is None: abort(404)
        db.session.execute(db.delete(NoteVersion).where(NoteVersion.note_id == note.id))
        db.session.delete(note); db.session.commit(); flash("Note deleted.", "success")
        return redirect(url_for("notes"))

    @app.route("/notes/<int:note_id>/toggle/<kind>", methods=["POST"])
    @login_required
    def toggle_note(note_id, kind):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == current_user.id))
        if note is None: abort(404)
        if kind == "favorite": note.is_favorite = not note.is_favorite
        elif kind == "archive": note.is_archived = not note.is_archived
        else: abort(404)
        db.session.commit(); flash("Note updated.", "success")
        return redirect(url_for("notes", archived="1" if request.args.get("archived") == "1" else None))

    @app.route("/notes/<int:note_id>/restore/<int:version_id>", methods=["POST"])
    @login_required
    def restore_note_version(note_id, version_id):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == current_user.id))
        version = db.session.scalar(db.select(NoteVersion).where(NoteVersion.id == version_id, NoteVersion.note_id == note_id))
        if note is None or version is None: abort(404)
        db.session.add(NoteVersion(note_id=note.id, title=note.title, content=note.content, category=note.category, tags=note.tags, note_type=note.note_type, related_titles=note.related_titles, review_date=note.review_date))
        note.title, note.content, note.category, note.tags, note.note_type = version.title, version.content, version.category, version.tags, version.note_type
        note.related_titles, note.review_date = version.related_titles, version.review_date
        db.session.commit(); flash("Previous version restored.", "success")
        return redirect(url_for("edit_note", note_id=note.id))

    @app.route("/notes/export/<fmt>")
    @login_required
    def export_notes(fmt):
        notes = db.session.scalars(db.select(Note).where(Note.user_id == current_user.id, Note.is_archived.is_(False)).order_by(Note.title)).all()
        if fmt not in ["txt", "md"]: abort(404)
        body = "\n\n".join((f"# {n.title}\n\nCategory: {n.category} | Tags: {n.tags or ''}\n\n{n.content}" if fmt == "md" else f"{n.title}\nCategory: {n.category} | Tags: {n.tags or ''}\n\n{n.content}") for n in notes)
        return Response(body, mimetype="text/markdown" if fmt == "md" else "text/plain", headers={"Content-Disposition": f"attachment; filename=memoryvault-notes.{fmt}"})

    @app.route("/planner", methods=["GET", "POST"])
    @login_required
    def planner():
        if request.method == "POST":
            title = request.form.get("title", "").strip(); details = request.form.get("details", "").strip()
            try: log_date = datetime.strptime(request.form.get("log_date", ""), "%Y-%m-%d").date()
            except ValueError: log_date = None
            if not title or len(title) > 200 or len(details) > 5000 or not log_date:
                flash("Enter a valid date and a title up to 200 characters.", "error")
            else:
                db.session.add(LearningLog(title=title, details=details, log_date=log_date, user_id=current_user.id)); db.session.commit(); flash("Learning log saved.", "success")
            return redirect(url_for("planner"))
        logs = db.session.scalars(db.select(LearningLog).where(LearningLog.user_id == current_user.id).order_by(LearningLog.log_date.desc())).all()
        unfinished = db.session.scalars(db.select(Task).where(Task.user_id == current_user.id, Task.status == "Pending").order_by(Task.due_date.asc())).all()
        completed = db.session.scalars(db.select(Task).where(Task.user_id == current_user.id, Task.status == "Completed").order_by(Task.completed_at.desc(), Task.created_at.desc()).limit(50)).all()
        week_start = date.today() - timedelta(days=date.today().weekday())
        week_tasks = db.session.scalars(db.select(Task).where(Task.user_id == current_user.id, Task.completed_at >= datetime.combine(week_start, datetime.min.time()))).all()
        return render_template("planner.html", logs=logs, unfinished=unfinished, completed=completed, today=date.today(), week_start=week_start, week_logs=sum(1 for log in logs if log.log_date >= week_start), week_completed=len(week_tasks))

    @app.route("/notes/<int:note_id>/review", methods=["POST"])
    @login_required
    def set_note_review(note_id):
        note = db.session.scalar(db.select(Note).where(Note.id == note_id, Note.user_id == current_user.id))
        if note is None: abort(404)
        date_text = request.form.get("review_date", "").strip()
        try:
            note.review_date = datetime.strptime(date_text, "%Y-%m-%d").date() if date_text else None
        except ValueError:
            flash("Enter a valid revision date.", "error")
            return redirect(url_for("notes"))
        db.session.commit()
        flash("Revision reminder updated.", "success")
        return redirect(url_for("notes"))

    # ---------------- LOGOUT ----------------

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        flash("You have logged out successfully.", "success")
        return redirect(url_for("home"))

    @app.errorhandler(404)
    def not_found(_error):
        return render_template_string("<main style='font-family:Arial;max-width:640px;margin:10vh auto;padding:24px'><h1>Page not found</h1><p>This page or record is unavailable.</p><a href='{{ url_for('dashboard') if current_user.is_authenticated else url_for('home') }}'>Return to MemoryVault</a></main>"), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template_string("<main style='font-family:Arial;max-width:640px;margin:10vh auto;padding:24px'><h1>Something went wrong</h1><p>Your request could not be completed. Please try again.</p><a href='{{ url_for('dashboard') if current_user.is_authenticated else url_for('home') }}'>Return to MemoryVault</a></main>"), 500

    # ---------------- DATABASE TABLES ----------------

    with app.app_context():
        db.create_all()
        # Lightweight SQLite migration for databases created before these features.
        from sqlalchemy import inspect
        columns = {c["name"] for c in inspect(db.engine).get_columns("notes")}
        with db.engine.begin() as connection:
            if "is_favorite" not in columns: connection.exec_driver_sql("ALTER TABLE notes ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT FALSE")
            if "is_archived" not in columns: connection.exec_driver_sql("ALTER TABLE notes ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE")
            if "related_titles" not in columns: connection.exec_driver_sql("ALTER TABLE notes ADD COLUMN related_titles VARCHAR(500)")
            if "review_date" not in columns: connection.exec_driver_sql("ALTER TABLE notes ADD COLUMN review_date DATE")
        task_columns = {c["name"] for c in inspect(db.engine).get_columns("tasks")}
        with db.engine.begin() as connection:
            if "completed_at" not in task_columns: connection.exec_driver_sql("ALTER TABLE tasks ADD COLUMN completed_at DATETIME")
        version_columns = {c["name"] for c in inspect(db.engine).get_columns("note_versions")}
        with db.engine.begin() as connection:
            if "related_titles" not in version_columns: connection.exec_driver_sql("ALTER TABLE note_versions ADD COLUMN related_titles VARCHAR(500)")
            if "review_date" not in version_columns: connection.exec_driver_sql("ALTER TABLE note_versions ADD COLUMN review_date DATE")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
