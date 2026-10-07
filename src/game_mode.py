import re
import time
from collections import deque, Counter
from typing import Optional, Dict, List, Tuple

BUTTON_MAP = {
    "a": "a",
    "b": "b",
    "start": "start",
    "select": "select",
    "up": "up",
    "u": "up",
    "oben": "up",
    "down": "down",
    "d": "down",
    "unten": "down",
    "left": "left",
    "l": "left",
    "links": "left",
    "right": "right",
    "r": "right",
    "rechts": "right",
    "wait": "wait",
}

VALID_BUTTONS = {"a", "b", "start", "select", "up", "down", "left", "right", "wait"}

# Pattern for commands with repeat count (e.g. a3, up2, left4)
COMMAND_REGEX = re.compile(r"^([a-zA-Z]+)([1-9])?$")

class ParsedInput:
    def __init__(self, raw: str, user: str, source: str = "web"):
        self.raw = raw.strip().lower()
        self.user = user
        self.source = source  # "web" or "twitch"
        self.timestamp = time.time()
        
        self.is_mode_vote: bool = False
        self.mode_vote: Optional[str] = None
        
        self.is_button: bool = False
        self.button: Optional[str] = None
        self.count: int = 1
        
        self._parse()

    def _parse(self):
        cleaned = self.raw.strip().lower()
        if cleaned in ("anarchy", "democracy"):
            self.is_mode_vote = True
            self.mode_vote = cleaned
            return

        # Split on whitespace, comma, or plus
        tokens = [t for t in re.split(r"[\s,+]+", cleaned) if t]
        if not tokens:
            return

        # 1. Check if token + number: e.g. ["down", "2"] or ["d", "3"]
        if len(tokens) == 2 and tokens[0] in BUTTON_MAP and tokens[1].isdigit():
            btn = BUTTON_MAP[tokens[0]]
            rep = min(int(tokens[1]), 9)
            self.is_button = True
            self.button = btn
            self.count = max(1, rep)
            return

        # 2. Check if all tokens are buttons of the same type: e.g. ["down", "down"] or ["d", "d", "d"]
        mapped_buttons = [BUTTON_MAP[t] for t in tokens if t in BUTTON_MAP]
        if mapped_buttons and len(mapped_buttons) == len(tokens):
            first_btn = mapped_buttons[0]
            if all(b == first_btn for b in mapped_buttons):
                self.is_button = True
                self.button = first_btn
                self.count = min(len(mapped_buttons), 9)
                return

        # 3. Check single token with attached number: e.g. "down2" or "a3"
        match = COMMAND_REGEX.match(tokens[0])
        if match:
            btn_key = match.group(1).lower()
            repeat_str = match.group(2)
            if btn_key in BUTTON_MAP:
                self.is_button = True
                self.button = BUTTON_MAP[btn_key]
                self.count = min(int(repeat_str), 9) if repeat_str else 1

class GameModeManager:
    def __init__(self, default_mode: str = "anarchy", democracy_seconds: int = 10, democracy_threshold: float = 0.6):
        self.current_mode = default_mode  # "anarchy" or "democracy"
        self.forced_mode: Optional[str] = None  # None, "anarchy", or "democracy"
        self.democracy_seconds = democracy_seconds
        self.democracy_threshold = democracy_threshold
        
        # Sliding window of last 50 mode votes
        self.mode_votes_window = deque(maxlen=50)
        # Prepopulate with default mode votes
        for _ in range(30):
            self.mode_votes_window.append(default_mode)
            
        # Democracy round state
        self.democracy_round_end = time.time() + self.democracy_seconds
        self.democracy_user_votes: Dict[str, str] = {}  # user -> button
        
        # History of executed commands (for UI live feed)
        self.recent_inputs: deque = deque(maxlen=25)
        self.total_inputs_count: int = 0

    def set_democracy_seconds(self, seconds: int):
        self.democracy_seconds = max(3, min(300, int(seconds)))

    def set_democracy_threshold(self, threshold: float):
        self.democracy_threshold = max(0.5, min(0.95, float(threshold)))

    def set_forced_mode(self, mode: Optional[str]):
        if mode in ("anarchy", "democracy"):
            self.forced_mode = mode
            self.current_mode = mode
        else:
            self.forced_mode = None

    def parse_command(self, raw_text: str, username: str, source: str = "web") -> Optional[ParsedInput]:
        parsed = ParsedInput(raw_text, username, source)
        if parsed.is_mode_vote or parsed.is_button:
            return parsed
        return None

    def register_mode_vote(self, vote: str) -> bool:
        """Records an anarchy/democracy vote. Returns True if mode changed."""
        self.mode_votes_window.append(vote)
        if self.forced_mode in ("anarchy", "democracy"):
            old_mode = self.current_mode
            self.current_mode = self.forced_mode
            return old_mode != self.current_mode

        dem_count = sum(1 for v in self.mode_votes_window if v == "democracy")
        total = len(self.mode_votes_window)
        ratio = dem_count / total if total > 0 else 0.0

        old_mode = self.current_mode
        if ratio >= self.democracy_threshold:
            self.current_mode = "democracy"
        elif ratio < 0.5:
            self.current_mode = "anarchy"
            
        return old_mode != self.current_mode

    def register_democracy_vote(self, user: str, button_command: str):
        """In democracy mode, records user's vote for the current round."""
        self.democracy_user_votes[user] = button_command

    def check_democracy_round(self) -> Optional[Tuple[str, int]]:
        """
        If democracy round time elapsed, calculate winner, reset timer, return (button, count).
        Returns None if round is still running.
        """
        now = time.time()
        if now < self.democracy_round_end:
            return None

        # Round is over, find winner
        winner_cmd = "wait"
        if self.democracy_user_votes:
            counter = Counter(self.democracy_user_votes.values())
            winner_cmd = counter.most_common(1)[0][0]

        # Reset round
        self.democracy_user_votes.clear()
        self.democracy_round_end = now + self.democracy_seconds

        # Parse winner command
        dummy = ParsedInput(winner_cmd, "Democracy", "system")
        if dummy.is_button and dummy.button:
            return (dummy.button, dummy.count)
        return ("wait", 1)

    def get_democracy_tally(self) -> List[Dict]:
        """Returns sorted vote percentages for the current democracy round."""
        total = len(self.democracy_user_votes)
        if total == 0:
            return []
        counter = Counter(self.democracy_user_votes.values())
        return [
            {"command": cmd, "votes": count, "percent": round((count / total) * 100, 1)}
            for cmd, count in counter.most_common(5)
        ]

    def record_execution(self, button: str, count: int, user: str, source: str):
        self.total_inputs_count += 1
        display_cmd = f"{button.upper()}" if count == 1 else f"{button.upper()} x{count}"
        self.recent_inputs.appendleft({
            "command": display_cmd,
            "button": button,
            "count": count,
            "user": user,
            "source": source,
            "mode": self.current_mode,
            "time": time.strftime("%H:%M:%S")
        })

    def get_status(self) -> Dict:
        dem_count = sum(1 for v in self.mode_votes_window if v == "democracy")
        total = len(self.mode_votes_window)
        dem_percent = round((dem_count / total * 100) if total > 0 else 0.0, 1)
        anarchy_percent = round(100.0 - dem_percent, 1)

        democracy_remaining = max(0.0, round(self.democracy_round_end - time.time(), 1))

        return {
            "mode": self.current_mode,
            "forced_mode": self.forced_mode,
            "anarchy_percent": anarchy_percent,
            "democracy_percent": dem_percent,
            "democracy_seconds": self.democracy_seconds,
            "democracy_remaining_sec": democracy_remaining,
            "democracy_tally": self.get_democracy_tally(),
            "total_inputs": self.total_inputs_count,
            "recent_inputs": list(self.recent_inputs)
        }
