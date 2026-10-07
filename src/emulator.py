import io
import os
import re
import time
import shutil
import asyncio
import logging
from pathlib import Path
from typing import Optional, List
from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = logging.getLogger("emulator")

class EmulatorManager:
    def __init__(self):
        self.pyboy = None
        self.rom_path: Optional[Path] = None
        self.rom_name: str = "None"
        self.is_running: bool = False
        self.latest_jpeg_bytes: bytes = b""
        self.frame_lock = asyncio.Lock()
        
        # Performance / stats
        self.fps_counter: float = 0.0
        self.frame_count: int = 0
        self.last_fps_calc = time.time()
        
        # Save state path
        self.save_dir = Path(settings.saves_dir)
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create save directory {self.save_dir}: {e}")
        self.auto_save_file = self.save_dir / "autosave.state"

        # Frame buffer placeholder dimensions (Game Boy standard)
        self.width = 160
        self.height = 144
        
        # Synthetic fallback animation counter if no ROM
        self.fallback_frame_idx = 0
        self.is_switching: bool = False

    def get_state_file(self, rom_path: Optional[Path] = None) -> Path:
        """Returns the save state file path for the given ROM, with legacy fallback."""
        target = rom_path or self.rom_path
        if target:
            specific = self.save_dir / f"{target.stem}.state"
            if specific.exists():
                return specific
            # Only match legacy autosave.state if this exact ROM is pokemon_rot
            if target.stem == "pokemon_rot":
                legacy = self.save_dir / "autosave.state"
                if legacy.exists():
                    return legacy
            return specific
        return self.save_dir / "autosave.state"

    def get_game_title(self) -> str:
        """Derives a human-friendly game title from the loaded ROM filename."""
        if not self.rom_name or self.rom_name == "None" or "standby" in self.rom_name.lower() or "error" in self.rom_name.lower():
            return "Pokémon"

        stem = Path(self.rom_name).stem.lower()

        # Handle known Game Boy franchises
        if "pokemon" in stem or "pokémon" in stem:
            for edition in ("gold", "silber", "silver", "kristall", "crystal", "rot", "red", "blau", "blue", "gelb", "yellow"):
                if edition in stem:
                    return f"Pokémon {edition.capitalize()}"
            return "Pokémon"
        elif "tetris" in stem:
            return "Tetris"
        elif "dr_mario" in stem or "dr mario" in stem or "drmario" in stem:
            return "Dr. Mario"
        elif "mario" in stem:
            if "land" in stem:
                return "Super Mario Land"
            return "Super Mario"
        elif "zelda" in stem:
            return "Zelda"
        elif "kirby" in stem:
            return "Kirby"
        elif "metroid" in stem:
            return "Metroid"
        elif "donkey" in stem or "kong" in stem:
            return "Donkey Kong"
        elif "wario" in stem:
            return "Wario Land"
        elif "megaman" in stem or "mega_man" in stem:
            return "Mega Man"

        # General fallback: clean up brackets, underscores, and dashes
        cleaned = re.sub(r'[\(\[\{].*?[\)\]\}]', '', Path(self.rom_name).stem)
        cleaned = cleaned.replace('_', ' ').replace('-', ' ').strip()
        words = cleaned.split()
        if words:
            return " ".join(w.capitalize() for w in words)
        return "Game Boy"

    def list_available_roms(self) -> List[str]:
        """Returns a list of all .gb and .gbc ROM filenames available in rom_dir."""
        rom_dir = Path(settings.rom_dir)
        if not rom_dir.exists():
            return []
        valid_extensions = {".gb", ".gbc"}
        roms = [f.name for f in rom_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]
        return sorted(roms, key=lambda s: s.lower())

    def discover_rom(self) -> Optional[Path]:
        """Finds ROM from admin config, environment ROM_PATH, or scans the rom directory."""
        rom_dir = Path(settings.rom_dir)
        if not rom_dir.exists():
            rom_dir.mkdir(parents=True, exist_ok=True)
            return None

        # 1. Configured via Admin console
        try:
            from src.admin import admin_manager
            if admin_manager.config.selected_rom:
                cand = rom_dir / admin_manager.config.selected_rom
                if cand.is_file():
                    return cand
        except Exception:
            pass

        # 2. Specified via ROM_PATH env
        if settings.rom_path and Path(settings.rom_path).is_file():
            return Path(settings.rom_path)

        # 3. Look for .gb and .gbc files
        valid_extensions = {".gb", ".gbc"}
        candidates: List[Path] = []
        for file in rom_dir.iterdir():
            if file.is_file() and file.suffix.lower() in valid_extensions:
                candidates.append(file)

        if not candidates:
            return None

        # Prefer files with "pokemon" or "pokémon" in name
        pokemon_roms = [c for c in candidates if "pokemon" in c.name.lower()]
        if pokemon_roms:
            return pokemon_roms[0]

        return sorted(candidates, key=lambda c: c.name.lower())[0]

    def _sync_saves_from_storage(self, rom_path: Path):
        """Restore .sav, .ram, and .rtc files from saves_dir next to the ROM so PyBoy loads them."""
        for ext in (".sav", ".ram", ".rtc"):
            for pattern in (rom_path.with_suffix(ext), Path(f"{rom_path}{ext}")):
                central = self.save_dir / pattern.name
                if central.exists():
                    try:
                        if not pattern.exists() or (central.stat().st_mtime > pattern.stat().st_mtime):
                            shutil.copy2(central, pattern)
                            logger.info(f"Loaded existing save from {central} to {pattern}")
                    except Exception as e:
                        logger.error(f"Error copying save {central}: {e}")

    def _sync_saves_to_storage(self, rom_path: Path):
        """Persist battery save (.sav/.ram) and real-time clock (.rtc) files into saves_dir volume."""
        for ext in (".sav", ".ram", ".rtc"):
            for pattern in (rom_path.with_suffix(ext), Path(f"{rom_path}{ext}")):
                if pattern.exists():
                    central = self.save_dir / pattern.name
                    try:
                        shutil.copy2(pattern, central)
                        logger.debug(f"Saved battery save to {central}")
                    except Exception as e:
                        logger.error(f"Error persisting save file: {e}")

    def initialize(self):
        found = self.discover_rom()
        if not found:
            logger.warning("No .gb or .gbc ROM found in rom directory. Running in interactive Standby mode.")
            self.rom_name = "Standby (No ROM found)"
            self._update_fallback_frame()
            return

        self.rom_path = found
        self.rom_name = found.name
        logger.info(f"Loading ROM: {self.rom_path}")

        try:
            from pyboy import PyBoy
            self._sync_saves_from_storage(self.rom_path)
            
            # Start PyBoy in headless null window
            is_cgb = self.rom_path.suffix.lower() == ".gbc"
            kwargs = {"window": "null"}
            if is_cgb:
                kwargs["cgb"] = True
            self.pyboy = PyBoy(str(self.rom_path), **kwargs)
            self.pyboy.set_emulation_speed(settings.emulation_speed)
            
            # Check for saved state
            state_file = self.get_state_file(self.rom_path)
            if state_file.exists():
                try:
                    with open(state_file, "rb") as f:
                        self.pyboy.load_state(f)
                    logger.info(f"Restored saved state for {self.rom_name} from {state_file.name}.")
                except Exception as e:
                    logger.warning(f"Could not load state file {state_file}: {e}")

            logger.info("PyBoy emulator initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PyBoy emulator: {e}", exc_info=True)
            self.pyboy = None
            self.rom_name = f"Error: {e}"

    def switch_rom(self, rom_name: str) -> bool:
        """Dynamically switches active ROM without restarting the server."""
        rom_dir = Path(settings.rom_dir)
        target = rom_dir / rom_name
        if not target.is_file():
            logger.warning(f"Requested ROM not found: {target}")
            return False

        logger.info(f"Initiating ROM switch to: {rom_name}")
        self.is_switching = True

        try:
            # 1. Auto-save current progress and stop old PyBoy instance
            if self.pyboy is not None:
                try:
                    self.save_state()
                except Exception as e:
                    logger.warning(f"Could not auto-save state before ROM switch: {e}")
                try:
                    self.pyboy.stop()
                except Exception as e:
                    logger.warning(f"Error stopping previous PyBoy instance: {e}")
                self.pyboy = None

            # 2. Update ROM path and name
            self.rom_path = target
            self.rom_name = target.name

            # 3. Restore battery save from saves directory
            self._sync_saves_from_storage(self.rom_path)

            # 4. Initialize new PyBoy instance
            from pyboy import PyBoy
            is_cgb = self.rom_path.suffix.lower() == ".gbc"
            kwargs = {"window": "null"}
            if is_cgb:
                kwargs["cgb"] = True
            self.pyboy = PyBoy(str(self.rom_path), **kwargs)
            self.pyboy.set_emulation_speed(settings.emulation_speed)

            # 5. Restore saved state if exists
            state_file = self.get_state_file(self.rom_path)
            if state_file.exists():
                try:
                    with open(state_file, "rb") as f:
                        self.pyboy.load_state(f)
                    logger.info(f"Restored saved state for {self.rom_name} from {state_file.name}.")
                except Exception as e:
                    logger.warning(f"Could not load state file {state_file}: {e}")

            logger.info(f"Successfully switched to ROM: {self.rom_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to switch to ROM {rom_name}: {e}", exc_info=True)
            self.pyboy = None
            self.rom_name = f"Error: {e}"
            return False
        finally:
            self.is_switching = False

    def _update_fallback_frame(self):
        """Draws a stylish retro Game Boy standby screen when no ROM is mounted."""
        self.fallback_frame_idx += 1
        
        # Classic Game Boy 4-shade greenish palette
        c_dark = (15, 56, 15)
        c_mid = (48, 98, 48)
        c_light = (139, 172, 15)
        c_bg = (155, 188, 15)
        
        img = Image.new("RGB", (self.width, self.height), color=c_bg)
        draw = ImageDraw.Draw(img)
        
        # Header banner
        draw.rectangle([(0, 0), (self.width, 20)], fill=c_dark)
        draw.text((16, 5), "TWITCH PLAYS", fill=c_bg)
        
        # Frame border
        draw.rectangle([(4, 24), (self.width - 5, self.height - 5)], outline=c_mid, width=2)
        
        # Animated Pokeball
        cx, cy = 80, 56
        r = 16
        # Pokeball outer circle
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=c_mid, outline=c_dark, width=2)
        # Center dividing line
        draw.line([(cx - r, cy), (cx + r, cy)], fill=c_dark, width=2)
        # Center button
        btn_r = 5
        pulse = 1 if (self.fallback_frame_idx // 15) % 2 == 0 else 0
        draw.ellipse([(cx - btn_r, cy - btn_r), (cx + btn_r, cy + btn_r)], fill=c_bg, outline=c_dark, width=2)
        if pulse:
            draw.ellipse([(cx - 2, cy - 2), (cx + 2, cy + 2)], fill=c_dark)

        # Instructions
        draw.text((14, 82), "NO ROM MOUNTED", fill=c_dark)
        draw.text((10, 98), "Put .gb/.gbc file in", fill=c_mid)
        draw.text((18, 110), "./roms/ directory", fill=c_mid)
        draw.text((12, 126), "and restart container", fill=c_dark)

        bio = io.BytesIO()
        img.save(bio, format="JPEG", quality=85)
        self.latest_jpeg_bytes = bio.getvalue()

    def capture_frame(self):
        """Captures the current Game Boy screen and converts to JPEG bytes."""
        if getattr(self, "is_switching", False):
            self._update_fallback_frame()
            self.frame_count += 1
            return

        if self.pyboy is not None:
            try:
                # PyBoy 2.x provides pyboy.screen.image as PIL Image
                pil_image = getattr(self.pyboy.screen, "image", None)
                if pil_image is None:
                    # Fallback via ndarray
                    import numpy as np
                    arr = self.pyboy.screen.ndarray
                    pil_image = Image.fromarray(arr)

                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                bio = io.BytesIO()
                # Gameboy is 160x144, JPEG compression is fast and tiny
                pil_image.save(bio, format="JPEG", quality=80)
                self.latest_jpeg_bytes = bio.getvalue()
            except Exception as e:
                logger.error(f"Error capturing frame: {e}")
        else:
            self._update_fallback_frame()

        self.frame_count += 1
        now = time.time()
        elapsed = now - self.last_fps_calc
        if elapsed >= 1.0:
            self.fps_counter = round(self.frame_count / elapsed, 1)
            self.frame_count = 0
            self.last_fps_calc = now

    async def press_button(self, button: str, count: int = 1, hold_duration: Optional[float] = None):
        """
        Executes button input in PyBoy.
        For directional buttons (up, down, left, right), if count > 1 (e.g. 'down down'),
        the button is HELD continuously for the combined duration of all steps
        so the player character walks fluidly without stuttering or stopping.
        For action buttons (a, b, start, select), distinct presses are sent.
        """
        if getattr(self, "is_switching", False):
            return

        if button == "wait":
            await asyncio.sleep(0.3)
            return

        valid_buttons = {"a", "b", "start", "select", "up", "down", "left", "right"}
        if button not in valid_buttons:
            logger.warning(f"Invalid button request: {button}")
            return

        if self.pyboy is None:
            logger.info(f"[Standby Mode] Virtual button pressed: {button} x{count}")
            await asyncio.sleep(0.1)
            return

        # Directional buttons: hold continuously for count * step_duration
        if button in {"up", "down", "left", "right"}:
            # Standard Gen 1 walk: 16 frames @ 60 FPS = ~0.266s per tile step
            step_duration = hold_duration or 0.26
            total_hold = step_duration * count

            try:
                if hasattr(self.pyboy, "button_press"):
                    self.pyboy.button_press(button)
                else:
                    self.pyboy.button(button)
            except Exception as e:
                logger.error(f"Failed to press button {button}: {e}")

            # Hold button continuously for all steps!
            await asyncio.sleep(total_hold)

            try:
                if hasattr(self.pyboy, "button_release"):
                    self.pyboy.button_release(button)
            except Exception as e:
                logger.error(f"Failed to release button {button}: {e}")

            # Small buffer between movements
            await asyncio.sleep(0.05)

        else:
            # Action buttons (A, B, Start, Select): distinct sequential taps
            press_duration = hold_duration or 0.15
            for _ in range(count):
                try:
                    if hasattr(self.pyboy, "button_press"):
                        self.pyboy.button_press(button)
                    else:
                        self.pyboy.button(button)
                except Exception as e:
                    logger.error(f"Failed to press button {button}: {e}")

                await asyncio.sleep(press_duration)

                try:
                    if hasattr(self.pyboy, "button_release"):
                        self.pyboy.button_release(button)
                except Exception as e:
                    logger.error(f"Failed to release button {button}: {e}")

                await asyncio.sleep(0.08)

    def tick_frames(self, count: int = 1):
        """Advances emulator ticks."""
        if getattr(self, "is_switching", False):
            return
        if self.pyboy is not None:
            for _ in range(count):
                self.pyboy.tick()

    def save_state(self) -> bool:
        """Saves current emulator state to disk."""
        if self.pyboy is None or self.rom_path is None:
            return False
        try:
            state_file = self.save_dir / f"{self.rom_path.stem}.state"
            tmp_save = state_file.with_suffix(".tmp")
            with open(tmp_save, "wb") as f:
                self.pyboy.save_state(f)
            tmp_save.replace(state_file)
            
            self._sync_saves_to_storage(self.rom_path)
                
            logger.info(f"Successfully persisted emulator state and battery save for {self.rom_name}.")
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def load_state(self) -> bool:
        """Loads state from save file for the current ROM."""
        if self.pyboy is None or self.rom_path is None:
            return False
        state_file = self.get_state_file(self.rom_path)
        if not state_file.exists():
            return False
        try:
            with open(state_file, "rb") as f:
                self.pyboy.load_state(f)
            logger.info(f"Successfully reloaded emulator state from {state_file.name}.")
            return True
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return False

    def set_speed(self, speed: int):
        """Sets emulation speed factor (1 = normal, 2 = 2x, etc.)."""
        if self.pyboy is not None:
            spd = max(1, min(5, int(speed)))
            self.pyboy.set_emulation_speed(spd)
            logger.info(f"Emulation speed updated to {spd}x")

    def shutdown(self):
        """Flushes battery saves and stops PyBoy."""
        logger.info("Shutting down emulator...")
        if self.pyboy is not None:
            try:
                self.save_state()
                self.pyboy.stop()
            except Exception as e:
                logger.error(f"Error stopping PyBoy: {e}")
            finally:
                self.pyboy = None

emulator = EmulatorManager()
