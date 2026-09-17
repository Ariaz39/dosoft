"""Tail the WAKFU game log and report combat events useful to DOSOFT."""

from pathlib import Path
import re
import threading
import time


# This is emitted when a fight is loaded, not at every turn.  It remains useful
# for diagnostics but deliberately is not used to trigger autofocus.
FIGHTER_EFFECTS_PATTERN = re.compile(
    r"Unserializing effects for fighter\s+(?P<fighter_id>\d+)", re.IGNORECASE
)
FIGHTER_IDENTITY_PATTERN = re.compile(
    r"\[_FL_\]\s+fightId=\d+\s+(?P<pseudo>.+?)\s+breed\s*:\s*\d+\s+"
    r"\[(?P<fighter_id>-?\d+)\]\s+isControlledByAI=false",
    re.IGNORECASE,
)
COMBAT_FIGHTER_PATTERN = re.compile(
    r"\[Information \(combat\)\]\s+(?P<pseudo>[^:]+):", re.IGNORECASE
)
TURN_BUDGET_PATTERN = re.compile(
    r"\[Information \(combat\)\]\s+\d+\s+secondes?\s+report(?:ées?|ees?)"
    r"\s+pour\s+le\s+tour\s+suivant", re.IGNORECASE
)
COMBAT_STARTED_PATTERN = re.compile(r"CREATION DU COMBAT|NetInFight Added", re.IGNORECASE)
COMBAT_ENDED_PATTERN = re.compile(r"\[FIGHT\]\s+End fight|NetInFight Removed", re.IGNORECASE)


class WakfuLogWatcher:
    def __init__(self, log_path, on_turn_candidate, on_fighter_identified=None, on_combat_state_change=None):
        self.log_path = Path(log_path)
        self.on_turn_candidate = on_turn_candidate
        self.on_fighter_identified = on_fighter_identified
        self.on_combat_state_change = on_combat_state_change
        self.last_combat_fighter = None
        self.last_combat_fighter_at = 0.0
        self.last_turn_key = None
        self.last_turn_at = 0.0

    def start(self):
        self._report_initial_combat_state()
        threading.Thread(target=self._tail_log, daemon=True, name="wakfu-log-watcher").start()

    def _report_initial_combat_state(self):
        """Seed combat state when DOSOFT starts in the middle of a fight."""
        if not self.on_combat_state_change or not self.log_path.exists():
            return
        try:
            with self.log_path.open("rb") as log_file:
                log_file.seek(0, 2)
                log_file.seek(max(0, log_file.tell() - 65536))
                recent_log = log_file.read().decode("utf-8", errors="replace")
            last_start = max((match.start() for match in COMBAT_STARTED_PATTERN.finditer(recent_log)), default=-1)
            last_end = max((match.start() for match in COMBAT_ENDED_PATTERN.finditer(recent_log)), default=-1)
            self.on_combat_state_change(last_start > last_end)
        except OSError:
            pass

    def _tail_log(self):
        stream = None
        last_size = 0
        while True:
            try:
                if not self.log_path.exists():
                    time.sleep(1)
                    continue

                current_size = self.log_path.stat().st_size
                if stream is None or current_size < last_size:
                    if stream:
                        stream.close()
                    stream = self.log_path.open("r", encoding="utf-8", errors="replace")
                    stream.seek(0, 2)

                line = stream.readline()
                if line:
                    if COMBAT_STARTED_PATTERN.search(line) and self.on_combat_state_change:
                        self.on_combat_state_change(True)
                    elif COMBAT_ENDED_PATTERN.search(line) and self.on_combat_state_change:
                        self.on_combat_state_change(False)

                    identity_match = FIGHTER_IDENTITY_PATTERN.search(line)
                    if identity_match and self.on_fighter_identified:
                        self.on_fighter_identified(
                            identity_match.group("fighter_id"),
                            identity_match.group("pseudo").strip(),
                        )
                    combat_match = COMBAT_FIGHTER_PATTERN.search(line)
                    if combat_match:
                        self.last_combat_fighter = combat_match.group("pseudo").strip()
                        self.last_combat_fighter_at = time.monotonic()

                    # WAKFU writes the active fighter's effects, then the time
                    # carried over to its new turn.  The time line itself has no
                    # character ID, so pair it with the immediately preceding
                    # named combat line.  Some clients duplicate those lines.
                    if TURN_BUDGET_PATTERN.search(line):
                        elapsed = time.monotonic() - self.last_combat_fighter_at
                        if self.last_combat_fighter and elapsed <= 2:
                            now = time.monotonic()
                            if self.on_turn_candidate and (
                                self.last_turn_key != self.last_combat_fighter
                                or now - self.last_turn_at > 2
                            ):
                                self.on_turn_candidate(self.last_combat_fighter)
                                self.last_turn_key = self.last_combat_fighter
                                self.last_turn_at = now
                else:
                    time.sleep(0.15)
                last_size = current_size
            except OSError:
                if stream:
                    stream.close()
                    stream = None
                time.sleep(1)
