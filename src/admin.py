import os
import json
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field

from src.config import settings

logger = logging.getLogger("admin")

class AdminConfig(BaseModel):
    admin_password: str = Field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", "admin"))
    show_rom_name: bool = Field(default_factory=lambda: os.getenv("SHOW_ROM_NAME", "false").lower() in ("true", "1", "yes"))
    democracy_round_seconds: int = Field(default_factory=lambda: settings.democracy_round_seconds)
    democracy_threshold: float = Field(default_factory=lambda: settings.democracy_vote_threshold)
    user_vote_cooldown: float = 0.0  # seconds between inputs per user (0.0 = unlimited)
    queue_input_delay: float = 0.15   # button hold duration in seconds
    queue_paused: bool = False
    forced_mode: Optional[str] = None # None, "anarchy", "democracy"
    selected_rom: Optional[str] = None
    emulation_speed: int = Field(default_factory=lambda: settings.emulation_speed)

class AdminManager:
    def __init__(self):
        self.config = AdminConfig()
        self.config_file = Path(settings.saves_dir) / "admin_settings.json"
        self.user_last_input: Dict[str, float] = {}
        self.load()

    def load(self):
        """Loads persistent admin configuration from saves directory."""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                # Update current config with loaded values
                for k, v in data.items():
                    if hasattr(self.config, k):
                        setattr(self.config, k, v)
                logger.info(f"Loaded admin configuration from {self.config_file}")
            except Exception as e:
                logger.warning(f"Could not load admin config from {self.config_file}: {e}")

    def save(self):
        """Persists current admin configuration to disk."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            self.config_file.write_text(self.config.model_dump_json(indent=2), encoding="utf-8")
            logger.info("Admin configuration saved to disk.")
        except Exception as e:
            logger.error(f"Failed to persist admin config: {e}")

    def verify_password(self, password: Optional[str]) -> bool:
        if not password:
            return False
        return password.strip() == self.config.admin_password

    def check_user_cooldown(self, user: str) -> Tuple[bool, float]:
        """
        Checks if a user is currently rate-limited by the cooldown setting.
        Returns (allowed: bool, remaining_seconds: float).
        """
        if self.config.user_vote_cooldown <= 0.0:
            return True, 0.0

        now = time.time()
        last = self.user_last_input.get(user, 0.0)
        elapsed = now - last
        if elapsed < self.config.user_vote_cooldown:
            return False, round(self.config.user_vote_cooldown - elapsed, 1)

        self.user_last_input[user] = now
        return True, 0.0

    def apply_to_systems(self, game_mode, emulator):
        """Propagates admin settings into live game mode and emulator instances."""
        game_mode.set_democracy_seconds(self.config.democracy_round_seconds)
        game_mode.set_democracy_threshold(self.config.democracy_threshold)
        game_mode.set_forced_mode(self.config.forced_mode)
        emulator.set_speed(self.config.emulation_speed)

    def update_settings(self, updates: Dict[str, Any], game_mode, emulator) -> Dict[str, Any]:
        """Validates, applies, and persists changes."""
        if "admin_password" in updates and updates["admin_password"]:
            self.config.admin_password = str(updates["admin_password"]).strip()

        if "show_rom_name" in updates:
            self.config.show_rom_name = bool(updates["show_rom_name"])

        if "democracy_round_seconds" in updates:
            val = int(updates["democracy_round_seconds"])
            self.config.democracy_round_seconds = max(3, min(300, val))

        if "democracy_threshold" in updates:
            val = float(updates["democracy_threshold"])
            self.config.democracy_threshold = max(0.5, min(0.95, val))

        if "user_vote_cooldown" in updates:
            val = float(updates["user_vote_cooldown"])
            self.config.user_vote_cooldown = max(0.0, min(60.0, val))

        if "queue_input_delay" in updates:
            val = float(updates["queue_input_delay"])
            self.config.queue_input_delay = max(0.05, min(1.0, val))

        if "queue_paused" in updates:
            self.config.queue_paused = bool(updates["queue_paused"])

        if "forced_mode" in updates:
            mode = updates["forced_mode"]
            if mode in ("anarchy", "democracy"):
                self.config.forced_mode = mode
            else:
                self.config.forced_mode = None

        if "emulation_speed" in updates:
            self.config.emulation_speed = max(1, min(5, int(updates["emulation_speed"])))

        if "selected_rom" in updates:
            self.config.selected_rom = str(updates["selected_rom"]).strip() if updates["selected_rom"] else None

        self.apply_to_systems(game_mode, emulator)
        self.save()
        return self.config.model_dump()

admin_manager = AdminManager()
