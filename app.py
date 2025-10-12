from app import create_app
from flask import redirect, url_for

app = create_app()

# 👇 Add this route
@app.route("/")
def index():
    return redirect(url_for("auth.login"))

if __name__ == "__main__":
    app.run(debug=True)
