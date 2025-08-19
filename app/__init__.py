from flask import Flask

def create_app():
    app = Flask(__name__)

    # import blueprints (each defines its own routes)
    from app.blueprints.main.views import main_bp
    from app.blueprints.customers.views import customers_bp
    from app.blueprints.bills.views import bills_bp

    blueprints = [main_bp, customers_bp, bills_bp]
    for bp in blueprints:
        app.register_blueprint(bp)   # no url_prefix; routes are full paths in views

    return app
