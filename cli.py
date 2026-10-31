import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from extensions import db
from models import User, CompanySetting


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create all database tables (convenient for the initial hackathon setup)."""
    db.create_all()
    if not CompanySetting.query.first():
        db.session.add(CompanySetting(company_name="Brightloop Software", currency="INR"))
        db.session.commit()
    click.echo("Database tables created and initial company settings checked.")


@click.command("create-admin")
@click.option("--name", prompt=True)
@click.option("--email", prompt=True)
@click.password_option()
@with_appcontext
def create_admin_command(name, email, password):
    """Create the first admin account. Only run this from a trusted terminal."""
    email = email.strip().lower()
    if User.query.filter_by(email=email).first():
        raise click.ClickException("An account with that email already exists.")
    user = User(name=name.strip(), email=email, role="admin", is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo(f"Admin account created for {email}.")


def register_commands(app):
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
