"""Toolbox: 教員向け授業補助ツール。他アプリは import しない。"""


def create_toolbox_blueprints() -> dict:
    from toolbox import admin as _admin  # noqa: F401
    from toolbox.routes import main_bp
    from toolbox.tools.random_pick.routes import register as register_random_pick
    from toolbox.tools.random_seats.routes import register as register_random_seats
    from toolbox.tools.talk_check.routes import register as register_talk_check
    from toolbox.tools.cnn10_lesson.routes import register as register_cnn10_lesson
    from toolbox.tools.timer.routes import register as register_timer

    register_timer(main_bp)
    register_cnn10_lesson(main_bp)
    register_random_pick(main_bp)
    register_random_seats(main_bp)
    register_talk_check(main_bp)
    return {"main": main_bp}


def register_cli(app) -> None:
    from toolbox.cli import register

    register(app)
