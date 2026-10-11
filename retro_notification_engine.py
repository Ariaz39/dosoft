"""Event-driven Windows notification detector for Dofus Retro.

The listener architecture and notification categories are inspired by Dracoon
by Slyss42 (MIT): https://github.com/Slyss42/Dracoon
DOSOFT keeps its own baseline, routing, diagnostics and safety guards.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
import unicodedata


try:  # Dracoon uses WinSDK; DOSOFT handles its Python 3.13 vector quirk below.
    import winsdk.windows.ui.notifications.management as notification_management
    import winsdk.windows.ui.notifications as notifications_api
    NOTIFICATION_BACKEND = "winsdk"
except ImportError:
    try:
        import winrt.windows.ui.notifications.management as notification_management
        import winrt.windows.ui.notifications as notifications_api
        NOTIFICATION_BACKEND = "winrt-secours"
    except ImportError:
        notification_management = None
        notifications_api = None
        NOTIFICATION_BACKEND = "indisponible"


RETRO_TITLE = re.compile(
    # Since Retro 1.49 the Windows toast title includes the client version,
    # for example: "Manall-lkt - Dofus Retro v1.49.5".
    r"^\s*(?P<pseudo>.+?)\s*-\s*dofus\s+r(?:e|é)tro"
    r"(?:\s+v(?:ersion\s*)?\d+(?:\.\d+)*(?:[-+._][\w-]+)*)?\s*$",
    re.IGNORECASE,
)
def _normalize_notification_text(text):
    """Make accents and punctuation irrelevant without translating content."""
    decomposed = unicodedata.normalize("NFKD", str(text or "").replace("’", "'"))
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def _rules(*localized_patterns):
    return tuple(
        (locale, re.compile(pattern, re.IGNORECASE))
        for locale, pattern in localized_patterns
    )


# Stable event identifiers are saved in settings.json. Detection phrases are
# deliberately separate and cover every Retro language pack: fr/en/es/pt/de/it/nl.
# Matching is accent-insensitive and targets actionable requests, so a completed
# or cancelled exchange is not confused with a new exchange proposal.
EVENT_RULES = {
    "combat": _rules(
        ("fr", r"\bde jouer\b"),
        ("en", r"\b(?:your turn(?: to play)?|turn to play)\b"),
        ("es", r"\b(?:te toca jugar|es el turno de)\b"),
        ("pt", r"\b(?:sua vez de jogar|e a vez de)\b"),
        ("de", r"\b(?:du bist am zug|du bist dran)\b"),
        ("it", r"\b(?:e il tuo turno|tocca a .+ giocare)\b"),
        ("nl", r"\b(?:jij bent aan de beurt|aan de beurt)\b"),
    ),
    "private_message": _rules(
        ("fr", r"^de\s+"), ("en", r"^from\s+"),
        ("es", r"^(?:de|desde)\s+"), ("pt", r"^de\s+"),
        ("de", r"^von\s+"), ("it", r"^da\s+"), ("nl", r"^van\s+"),
    ),
    "trade": _rules(
        ("fr", r"\bpropose.+(?:echange|echanger)\b"),
        ("en", r"\b(?:offers?.+(?:trade|exchange)|wants to trade)\b"),
        ("es", r"\bpropone.+intercambio\b"),
        ("pt", r"\b(?:propoe.+troca|quer trocar)\b"),
        ("de", r"\b(?:bietet.+tausch|mochte.+handeln)\b"),
        ("it", r"\bpropone.+scambio\b"),
        ("nl", r"\b(?:stelt.+ruil|wil.+handelen)\b"),
    ),
    "group": _rules(
        ("fr", r"\binvite.+rejoindre (?:son groupe|sa guilde)\b"),
        ("en", r"\binvit(?:es|ed).+join.+(?:group|guild)\b"),
        ("es", r"\binvita.+unirte.+(?:grupo|gremio)\b"),
        ("pt", r"\bconvida.+(?:entrar|juntar).+(?:grupo|guilda)\b"),
        ("de", r"\blad(?:t|et).+(?:gruppe|gilde).+ein\b"),
        ("it", r"\binvita.+(?:unirti|entrare).+(?:gruppo|gilda)\b"),
        ("nl", r"\bnodigt.+(?:groep|gilde)\b"),
    ),
    "challenge": _rules(
        ("fr", r"\bte defie\b"), ("en", r"\bchallenges you\b"),
        ("es", r"\bte desafia\b"), ("pt", r"\bdesafia voce\b"),
        ("de", r"\bfordert dich heraus\b"), ("it", r"\bti sfida\b"),
        ("nl", r"\bdaagt je uit\b"),
    ),
    "craft": _rules(
        ("fr", r"\b(?:talents d.artisan|rejoindre son atelier|objets ont ete fabriques)\b"),
        ("en", r"\b(?:crying out for your skills|join .+ workshop|all items have been created)\b"),
        ("es", r"\b(?:talentos de artesano|pasarte por su taller|objetos han sido fabricados)\b"),
        ("pt", r"\b(?:talentos de artesao|juntar.+oficina|itens foram fabricados)\b"),
        ("de", r"\b(?:handwerkstalente|werkstatt beitreten|gegenstande wurden hergestellt)\b"),
        ("it", r"\b(?:talenti da artigiano|unirti.+laboratorio|oggetti sono stati creati)\b"),
        ("nl", r"\b(?:ambachtelijke talenten|werkplaats deelnemen|voorwerpen zijn gemaakt)\b"),
    ),
    "pvp": _rules(
        ("fr", r"\bpercepteur.+est attaque\b"),
        ("en", r"\bperceptor.+is (?:being )?attacked\b"),
        ("es", r"\brecaudador.+esta siendo atacado\b"),
        ("pt", r"\bcoletor.+esta sendo atacado\b"),
        ("de", r"\bsteuereintreiber.+wird angegriffen\b"),
        ("it", r"\besattore.+viene attaccato\b"),
        ("nl", r"\bbelastinginner.+wordt aangevallen\b"),
    ),
}

# Compatibility for callers that need the ordered list of supported event IDs.
EVENT_PATTERNS = {
    event_type: tuple(pattern for _locale, pattern in rules)
    for event_type, rules in EVENT_RULES.items()
}


def parse_retro_notification(texts):
    """Return a normalized event from visible toast strings, or ``None``."""
    cleaned = [str(text or "").strip() for text in texts if str(text or "").strip()]
    pseudo = None
    title_index = None
    for index, text in enumerate(cleaned):
        match = RETRO_TITLE.match(text)
        if match:
            pseudo = match.group("pseudo").strip()
            title_index = index
            break
    if not pseudo:
        return None
    body_parts = [text for index, text in enumerate(cleaned) if index != title_index]
    body = " | ".join(body_parts)
    normalized_body = _normalize_notification_text(body)
    for event_type, rules in EVENT_RULES.items():
        for locale, pattern in rules:
            if pattern.search(normalized_body):
                return {
                    "pseudo": pseudo, "event_type": event_type,
                    "body": body, "locale": locale,
                }
    return None


def _collection_items(collection):
    """Read WinRT vectors without their broken Python 3.13 iterator wrapper."""
    get_at = getattr(collection, "get_at", None)
    size = getattr(collection, "size", None)
    if callable(get_at) and size is not None:
        return [get_at(index) for index in range(int(size))]
    return list(collection)


class RetroNotificationEngine:
    """One notification subscription with polling fallback and clean shutdown."""

    def __init__(self, on_detected, log, enabled_events=None, polling_only=False,
                 remove_after_read=True, fallback_seconds=2.0):
        self.on_detected = on_detected
        self.log = log
        self.set_enabled_events(enabled_events)
        self.polling_only = bool(polling_only)
        self.remove_after_read = bool(remove_after_read)
        self.fallback_seconds = max(0.5, float(fallback_seconds))
        self._stop_event = threading.Event()
        self._thread = None
        self._loop = None
        self._callback = None
        self._recent_events = {}

    def set_enabled_events(self, enabled_events):
        requested = EVENT_PATTERNS if enabled_events is None else enabled_events
        # frozenset replacement is atomic for the polling thread, including an
        # intentionally empty selection.
        self.enabled_events = frozenset(
            event_type for event_type in requested if event_type in EVENT_PATTERNS
        )

    @property
    def available(self):
        return notification_management is not None and notifications_api is not None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        if not self.available:
            self.log("[AUTOFOCUS RETRO] ECHEC backend notifications indisponible.")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main, daemon=True, name="retro-notification-engine"
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(lambda: None)

    def _thread_main(self):
        pythoncom = None
        try:
            import pythoncom as pythoncom_module
            pythoncom = pythoncom_module
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception as error:
            self.log(f"[AUTOFOCUS RETRO] COM STA indisponible : {type(error).__name__}:{error}")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._run_forever())
        finally:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    @staticmethod
    def _access_allowed(access):
        return getattr(access, "value", access) == 1

    @staticmethod
    def _notification_texts(notification):
        texts = []
        visual = notification.notification.visual
        for binding in _collection_items(visual.bindings):
            texts.extend(
                str(item.text or "").strip()
                for item in _collection_items(binding.get_text_elements())
            )
        return [text for text in texts if text]

    def _emit(self, notification, source):
        notification_id = getattr(notification, "id", "unknown")
        try:
            texts = self._notification_texts(notification)
            event = parse_retro_notification(texts)
        except Exception as error:
            self.log(
                f"[AUTOFOCUS RETRO] lecture impossible id={notification_id} "
                f"error={type(error).__name__}:{error}"
            )
            return False
        if not event:
            # Never persist unrelated notification text (mail, chat, etc.) in
            # DOSOFT's diagnostic file.
            self.log(f"[AUTOFOCUS RETRO] toast non-Rétro ou non reconnu ignoré id={notification_id}")
            return False
        if event["event_type"] not in self.enabled_events:
            self.log(
                f"[AUTOFOCUS RETRO] événement désactivé type={event['event_type']} "
                f"pseudo={event['pseudo']!r} langue={event.get('locale', '?')}"
            )
            # Disabled means no focus and no removal of the Windows banner.
            return False

        now = time.monotonic()
        semantic_key = (event["pseudo"].casefold(), event["event_type"], event["body"].casefold())
        previous = self._recent_events.get(semantic_key, 0.0)
        if now - previous < 0.75:
            self.log(f"[AUTOFOCUS RETRO] doublon ignoré pseudo={event['pseudo']!r}")
            return True
        self._recent_events[semantic_key] = now
        if len(self._recent_events) > 200:
            self._recent_events = {
                key: stamp for key, stamp in self._recent_events.items() if now - stamp < 60
            }
        self.log(
            f"[AUTOFOCUS RETRO] détecté source={source} type={event['event_type']} "
            f"pseudo={event['pseudo']!r} langue={event.get('locale', '?')} id={notification_id}"
        )
        self.on_detected(
            event["pseudo"], event["event_type"], source, event["body"], notification_id
        )
        return True

    async def _run_forever(self):
        while not self._stop_event.is_set():
            try:
                await self._listen_once()
            except asyncio.CancelledError:
                break
            except Exception as error:
                self.log(
                    f"[AUTOFOCUS RETRO] listener redémarré après "
                    f"{type(error).__name__}:{error}"
                )
                await asyncio.sleep(2)

    async def _listen_once(self):
        listener = notification_management.UserNotificationListener.current
        access = await listener.request_access_async()
        if not self._access_allowed(access):
            self.log(
                f"[AUTOFOCUS RETRO] permission notifications refusée code="
                f"{getattr(access, 'value', access)}"
            )
            await asyncio.sleep(5)
            return

        baseline = _collection_items(
            await listener.get_notifications_async(notifications_api.NotificationKinds.TOAST)
        )
        seen_ids = {notification.id for notification in baseline}
        self.log(
            f"[AUTOFOCUS RETRO] prêt backend={NOTIFICATION_BACKEND} "
            f"mode={'polling' if self.polling_only else 'événementiel'} "
            f"baseline={len(seen_ids)}"
        )
        wake_event = asyncio.Event()
        token = None

        if not self.polling_only:
            def on_notification_changed(_sender, _args):
                # WinRT may invoke this callback from another COM thread. Never
                # read or route a toast here; only wake the owning asyncio loop.
                try:
                    if self._loop and self._loop.is_running():
                        self._loop.call_soon_threadsafe(wake_event.set)
                except Exception:
                    pass

            self._callback = on_notification_changed
            try:
                token = listener.add_notification_changed(on_notification_changed)
            except Exception as error:
                self.log(
                    f"[AUTOFOCUS RETRO] abonnement événementiel indisponible, "
                    f"polling réactif 0,3 s actif : {type(error).__name__}:{error}"
                )

        try:
            while not self._stop_event.is_set():
                if token is not None:
                    try:
                        await asyncio.wait_for(wake_event.wait(), timeout=self.fallback_seconds)
                    except asyncio.TimeoutError:
                        source = "polling-secours"
                    else:
                        source = "événement-windows"
                    wake_event.clear()
                else:
                    source = "polling"
                    # Same responsive fallback principle as Dracoon: some
                    # Windows desktop contexts return E_ELEMENTNOTFOUND when
                    # subscribing even though reading notifications is allowed.
                    await asyncio.sleep(min(0.3, self.fallback_seconds))

                current = _collection_items(
                    await listener.get_notifications_async(
                        notifications_api.NotificationKinds.TOAST
                    )
                )
                current_ids = {notification.id for notification in current}
                for notification in current:
                    if notification.id in seen_ids:
                        continue
                    seen_ids.add(notification.id)
                    accepted = self._emit(notification, source)
                    if accepted and self.remove_after_read:
                        try:
                            listener.remove_notification(notification.id)
                        except Exception as error:
                            self.log(
                                f"[AUTOFOCUS RETRO] suppression toast impossible id="
                                f"{notification.id}: {type(error).__name__}:{error}"
                            )
                seen_ids.intersection_update(current_ids)
        finally:
            if token is not None:
                try:
                    listener.remove_notification_changed(token)
                except Exception:
                    pass
            self._callback = None
