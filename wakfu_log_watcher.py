"""Tail the WAKFU game log and report combat-turn candidate events."""

from pathlib import Path
import re
import threading
import time


FIGHTER_TURN_PATTERN = re.compile(
    r"Unserializing effects for fighter\s+(?P<fighter_id>\d+)", re.IGNORECASE
)
FIGHTER_IDENTITY_PATTERN = re.compile(
    r"\[_FL_\]\s+fightId=\d+\s+(?P<pseudo>.+?)\s+breed\s*:\s*\d+\s+"
    r"\[(?P<fighter_id>-?\d+)\]\s+isControlledByAI=false",
    re.IGNORECASE,
)


class WakfuLogWatcher:
    def __init__(self, log_path, on_fighter_turn, on_fighter_identified=None):
        self.log_path = Path(log_path)
        self.on_fighter_turn = on_fighter_turn
        self.on_fighter_identified = on_fighter_identified

    def start(self):
        threading.Thread(target=self._tail_log, daemon=True, name="wakfu-log-watcher").start()

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
                    identity_match = FIGHTER_IDENTITY_PATTERN.search(line)
                    if identity_match and self.on_fighter_identified:
                        self.on_fighter_identified(
                            identity_match.group("fighter_id"),
                            identity_match.group("pseudo").strip(),
                        )
                    match = FIGHTER_TURN_PATTERN.search(line)
                    if match:
                        self.on_fighter_turn(match.group("fighter_id"))
                else:
                    time.sleep(0.15)
                last_size = current_size
            except OSError:
                if stream:
                    stream.close()
                    stream = None
                time.sleep(1)
