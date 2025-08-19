from flask import Blueprint, render_template

customers_bp = Blueprint("customers", __name__, template_folder="templates")

@customers_bp.route("/customers")
def index():
    return render_template("customers/index.html")
