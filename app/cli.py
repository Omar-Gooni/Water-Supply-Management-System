import click
from flask.cli import with_appcontext

from app.extensions import db
from app.Auth.blueprints.auth.models import User


def _upsert_user(username, password, role):
    db.create_all()

    user = User.query.filter_by(username=username).first()
    if user is None:
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        action = "created"
    else:
        user.role = role
        user.set_password(password)
        action = "updated"

    db.session.commit()
    return action


def register_cli_commands(app):
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Create all tables for the current models."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True, help="Admin username")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Admin password")
    @with_appcontext
    def create_admin(username, password):
        """Create or promote a user to admin."""
        action = _upsert_user(username, password, "Admin")
        click.echo(f"Admin user '{username}' {action} successfully.")

    @app.cli.command("create-staff")
    @click.option("--username", prompt=True, help="Staff username")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Staff password")
    @with_appcontext
    def create_staff(username, password):
        """Create or promote a user to staff."""
        action = _upsert_user(username, password, "Staff")
        click.echo(f"Staff user '{username}' {action} successfully.")

    @app.cli.command("create-counter")
    @click.option("--username", prompt=True, help="Counter username")
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True, help="Counter password")
    @with_appcontext
    def create_counter(username, password):
        """Create or promote a user to counter."""
        action = _upsert_user(username, password, "Counter")
        click.echo(f"Counter user '{username}' {action} successfully.")
