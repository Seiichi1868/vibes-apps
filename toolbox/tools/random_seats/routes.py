from flask import render_template

from toolbox.auth import current_user, login_required
from toolbox.routes import tool_required
from toolbox.storage import list_classes


def register(bp):
    @bp.route("/random-seats")
    @login_required
    @tool_required("random_seats")
    def random_seats_page():
        return render_template(
            "toolbox/tools/random_seats.html",
            classes=list_classes(current_user()["id"]),
        )
