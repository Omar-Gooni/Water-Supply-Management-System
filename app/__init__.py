from datetime import datetime

from flask import Flask

from .config import Config
from .extensions import db, migrate


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)

    @app.context_processor
    def inject_current_year():
        return {"current_year": datetime.now().year}

    from app.utils.model_loader import import_submodules
    import app.Admin.blueprints as admin_pkg
    import app.Auth.blueprints as auth_pkg

    import_submodules(admin_pkg, "models")
    import_submodules(auth_pkg, "models")

    from .Auth import register_web_blueprints as register_auth_blueprints
    from .Admin import register_web_blueprints as register_admin_blueprints
    from .Staff import register_web_blueprints as register_staff_blueprints
    from .cli import register_cli_commands

    register_admin_blueprints(app)
    register_staff_blueprints(app)
    register_auth_blueprints(app)
    register_cli_commands(app)

    return app
