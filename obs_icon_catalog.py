"""Local icon catalogue used by the optional OBS Streamdeck extension."""

from resource_paths import resource_path


OBS_ICON_CATALOG = (
    ("globe", "Web"),
    ("eye", "Afficher"),
    ("eye-slash", "Masquer"),
    ("display", "Écran"),
    ("gamepad", "Jeu"),
    ("camera", "Caméra"),
    ("microphone", "Micro"),
    ("volume-xmark", "Muet"),
    ("pause", "Pause"),
    ("play", "Lecture"),
    ("rotate", "Relancer"),
    ("house", "Accueil"),
    ("comments", "Discussion"),
    ("image", "Image"),
    ("window-maximize", "Fenêtre"),
    ("shield-halved", "Sécurité"),
)

OBS_ICON_LABELS = dict(OBS_ICON_CATALOG)
DEFAULT_OBS_ICON = "globe"


def obs_icon_path(icon_id):
    safe_id = icon_id if icon_id in OBS_ICON_LABELS else DEFAULT_OBS_ICON
    return resource_path("resources", "skin", "streamdeck", "icons", f"{safe_id}.png")
