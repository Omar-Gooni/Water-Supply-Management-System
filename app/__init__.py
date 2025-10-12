from flask import Flask

from .config import Config
from .extensions import db, migrate

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    
        # ✅ AUTO-LOAD all models under Admin and User blueprints
    from app.utils.model_loader import import_submodules
    import app.Admin.blueprints as admin_pkg
    # import app.User.blueprints as user_pkg

    import_submodules(admin_pkg, "models")
    # import_submodules(user_pkg, "models")
    
    from .Auth import register_web_blueprints as register_auth_blueprints
    from .Admin import register_web_blueprints as register_admin_blueprints
    register_admin_blueprints(app)
    register_auth_blueprints(app)

    return app
