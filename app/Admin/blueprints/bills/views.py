from flask import Blueprint, render_template

bills_bp = Blueprint("bills", __name__, template_folder="templates")

@bills_bp.route("/bills")
def index():
    return render_template("bills/index.html")
