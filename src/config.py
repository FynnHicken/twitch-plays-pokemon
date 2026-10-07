import os
from pathlib import Path
from pydantic import BaseModel, Field

def _default_rom_dir() -> Path:
    env_val = os.getenv("ROM_DIR")
    if env_val:
        return Path(env_val)
    if Path("/app").exists() and os.access("/app", os.W_OK):
        return Path("/app/roms")
    return Path(__file__).resolve().parent.parent / "roms"

def _default_saves_dir() -> Path:
    env_val = os.getenv("SAVES_DIR")
    if env_val:
        return Path(env_val)
    if Path("/app").exists() and os.access("/app", os.W_OK):
        return Path("/app/saves")
    return Path(__file__).resolve().parent.parent / "saves"

class Settings(BaseModel):
    # Server configuration
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8080")))
    
    # Storage & Paths
    rom_dir: Path = Field(default_factory=_default_rom_dir)
    saves_dir: Path = Field(default_factory=_default_saves_dir)
    rom_path: str = Field(default_factory=lambda: os.getenv("ROM_PATH", ""))

    # Emulation & Stream
    target_fps: int = Field(default_factory=lambda: int(os.getenv("FPS", "30")))
    emulation_speed: int = Field(default_factory=lambda: int(os.getenv("EMULATION_SPEED", "1")))
    auto_save_interval: int = Field(default_factory=lambda: int(os.getenv("AUTO_SAVE_INTERVAL", "60")))
    
    # Game Modes & Rules
    default_mode: str = Field(default_factory=lambda: os.getenv("DEFAULT_MODE", "anarchy").lower())
    democracy_round_seconds: int = Field(default_factory=lambda: int(os.getenv("DEMOCRACY_INTERVAL", "10")))
    democracy_vote_threshold: float = Field(default_factory=lambda: float(os.getenv("DEMOCRACY_THRESHOLD", "0.6")))
    
    # Twitch IRC integration
    twitch_channel: str = Field(default_factory=lambda: os.getenv("TWITCH_CHANNEL", "").strip())
    twitch_token: str = Field(default_factory=lambda: os.getenv("TWITCH_TOKEN", "").strip())
    twitch_nick: str = Field(default_factory=lambda: os.getenv("TWITCH_NICK", "").strip())
    
    @property
    def is_twitch_enabled(self) -> bool:
        return bool(self.twitch_channel)

settings = Settings()
