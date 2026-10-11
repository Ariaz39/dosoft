"""Small, testable rules controlling optional background modules."""


def should_run_retro_autofocus(settings):
    return (
        settings.get("game_version") == "Rétro"
        and bool(settings.get("auto_focus_retro", False))
    )
