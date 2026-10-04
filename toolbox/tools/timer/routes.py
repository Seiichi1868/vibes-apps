from flask import render_template

from toolbox.auth import login_required
from toolbox.routes import tool_required


def register(bp):
    @bp.route("/timer")
    @login_required
    @tool_required("timer")
    def timer_page():
        return render_template("toolbox/tools/timer.html")
