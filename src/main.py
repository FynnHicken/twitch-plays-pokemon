import asyncio
import logging
import os
import re
import time
from urllib.parse import unquote
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import settings
from src.emulator import emulator
from src.game_mode import GameModeManager
from src.admin import admin_manager
from src.twitch_bot import TwitchBot

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("main")

# State & Managers
game_mode = GameModeManager(
    default_mode=settings.default_mode,
    democracy_seconds=settings.democracy_round_seconds,
    democracy_threshold=settings.democracy_vote_threshold
)

anarchy_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
connected_websockets: Set[WebSocket] = set()
background_tasks = []

def clear_anarchy_queue() -> int:
    cleared = 0
    while not anarchy_queue.empty():
        try:
            anarchy_queue.get_nowait()
            anarchy_queue.task_done()
            cleared += 1
        except (asyncio.QueueEmpty, ValueError):
            break
    return cleared

# Broadcast helper
async def broadcast_ws(message: Dict[str, Any]):
    dead = set()
    for ws in connected_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    for ws in dead:
        connected_websockets.discard(ws)

def get_full_status() -> Dict[str, Any]:
    status = game_mode.get_status()
    status["fps"] = emulator.fps_counter
    status["show_rom"] = admin_manager.config.show_rom_name
    if admin_manager.config.show_rom_name:
        status["rom"] = emulator.rom_name
    else:
        status["rom"] = "Aktiv"
    status["viewers"] = len(connected_websockets)
    status["queue_size"] = anarchy_queue.qsize()
    status["queue_paused"] = admin_manager.config.queue_paused
    status["user_cooldown"] = admin_manager.config.user_vote_cooldown
    game_title = emulator.get_game_title()
    status["game_title"] = game_title
    status["stream_title"] = f"TWITCH PLAYS {game_title.upper()}"
    status["page_title"] = f"Twitch Plays {game_title} - Docker Edition"
    return status

def handle_user_command(user: str, raw_text: str, source: str = "web"):
    """Entry point for commands coming from Web Chat or Twitch."""
    parsed = game_mode.parse_command(raw_text, user, source)
    if not parsed:
        return

    # Check user cooldown (spam protection)
    allowed, rem = admin_manager.check_user_cooldown(user)
    if not allowed:
        logger.debug(f"User {user} rate limited ({rem}s left)")
        return

    # 1. Mode vote (anarchy / democracy)
    if parsed.is_mode_vote and parsed.mode_vote:
        changed = game_mode.register_mode_vote(parsed.mode_vote)
        asyncio.create_task(broadcast_ws({
            "type": "mode_vote",
            "user": user,
            "vote": parsed.mode_vote,
            "source": source,
            "status": get_full_status()
        }))
        if changed:
            logger.info(f"Game mode shifted to: {game_mode.current_mode.upper()}")
            asyncio.create_task(broadcast_ws({
                "type": "system_announcement",
                "text": f"Mode changed to {game_mode.current_mode.upper()}!"
            }))
        return

    # 2. Button command
    if parsed.is_button and parsed.button:
        if admin_manager.config.queue_paused:
            logger.debug("Input queue is paused by admin, ignoring command.")
            return

        if game_mode.current_mode == "anarchy":
            try:
                anarchy_queue.put_nowait(parsed)
            except asyncio.QueueFull:
                logger.warning("Anarchy queue is full, dropping command.")
        else:
            # Democracy mode: record vote for current round
            game_mode.register_democracy_vote(user, f"{parsed.button}{parsed.count if parsed.count > 1 else ''}")
            asyncio.create_task(broadcast_ws({
                "type": "democracy_vote",
                "user": user,
                "command": parsed.raw,
                "status": get_full_status()
            }))

# Background task loops
async def emulation_loop():
    """Main Game Boy frame update loop running at target FPS."""
    frame_interval = 1.0 / max(10, settings.target_fps)
    while True:
        start_time = time.time()
        
        # Advance emulator ticks (approx 2 ticks per 30fps frame to match 60Hz)
        ticks_per_frame = max(1, int(60 / settings.target_fps))
        emulator.tick_frames(ticks_per_frame)
        emulator.capture_frame()

        elapsed = time.time() - start_time
        sleep_dur = max(0.001, frame_interval - elapsed)
        await asyncio.sleep(sleep_dur)

async def input_executor_loop():
    """Consumes commands from anarchy queue or executes democracy winners."""
    while True:
        if admin_manager.config.queue_paused:
            await asyncio.sleep(0.2)
            continue

        if game_mode.current_mode == "anarchy":
            try:
                # Wait for next anarchy command
                parsed = await asyncio.wait_for(anarchy_queue.get(), timeout=0.1)
                button = parsed.button
                count = parsed.count

                # If directional, check for consecutive same-direction commands to hold continuously
                chained_events = []
                if button in ("up", "down", "left", "right"):
                    while not anarchy_queue.empty() and count < 6:
                        next_parsed = anarchy_queue._queue[0]
                        if next_parsed.is_button and next_parsed.button == button:
                            anarchy_queue.get_nowait()
                            anarchy_queue.task_done()
                            count += next_parsed.count
                            chained_events.append(next_parsed)
                        else:
                            break

                # Execute on emulator (holds button continuously for all steps!)
                await emulator.press_button(button, count)
                game_mode.record_execution(button, parsed.count, parsed.user, parsed.source)

                # Broadcast executed command to UI
                await broadcast_ws({
                    "type": "executed_input",
                    "button": button,
                    "count": count,
                    "user": parsed.user,
                    "source": parsed.source,
                    "mode": "anarchy",
                    "status": get_full_status()
                })
                anarchy_queue.task_done()

                for ch in chained_events:
                    game_mode.record_execution(button, ch.count, ch.user, ch.source)
                    await broadcast_ws({
                        "type": "executed_input",
                        "button": button,
                        "count": ch.count,
                        "user": ch.user,
                        "source": ch.source,
                        "mode": "anarchy",
                        "status": get_full_status()
                    })
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error executing anarchy input: {e}")
        else:
            # Democracy mode
            round_result = game_mode.check_democracy_round()
            if round_result:
                button, count = round_result
                if button != "wait":
                    await emulator.press_button(button, count)
                
                game_mode.record_execution(button, count, "Democracy Vote", "democracy")
                await broadcast_ws({
                    "type": "executed_input",
                    "button": button,
                    "count": count,
                    "user": "Democracy",
                    "source": "democracy",
                    "mode": "democracy",
                    "status": get_full_status()
                })
            await asyncio.sleep(0.1)

async def status_broadcast_loop():
    """Regularly sends state updates to all web clients."""
    while True:
        await asyncio.sleep(1.0)
        await broadcast_ws({
            "type": "status_update",
            "status": get_full_status()
        })

async def auto_save_loop():
    """Periodically saves game state to disk."""
    while True:
        await asyncio.sleep(settings.auto_save_interval)
        if emulator.pyboy is not None:
            emulator.save_state()

# Twitch IRC Bot instance
twitch_bot = TwitchBot(
    channel=settings.twitch_channel,
    oauth_token=settings.twitch_token,
    nickname=settings.twitch_nick,
    on_message_callback=lambda user, text: handle_user_command(user, text, source="twitch")
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Twitch Plays Pokemon server...")
    emulator.initialize()
    admin_manager.apply_to_systems(game_mode, emulator)

    # Launch background tasks
    tasks = [
        asyncio.create_task(emulation_loop()),
        asyncio.create_task(input_executor_loop()),
        asyncio.create_task(status_broadcast_loop()),
        asyncio.create_task(auto_save_loop())
    ]
    if settings.is_twitch_enabled:
        tasks.append(asyncio.create_task(twitch_bot.start()))

    yield

    logger.info("Shutting down Twitch Plays Pokemon...")
    for t in tasks:
        t.cancel()
    if settings.is_twitch_enabled:
        await twitch_bot.stop()
    emulator.shutdown()

app = FastAPI(title="Twitch Plays Pokemon", lifespan=lifespan)

# Static files
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Twitch Plays Pokemon is running!</h1>")

@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon():
    favicon_file = static_dir / "favicon.ico"
    if favicon_file.exists():
        return FileResponse(favicon_file, media_type="image/x-icon")
    return Response(status_code=204)

async def frame_stream_generator():
    """Generator for MJPEG stream."""
    while True:
        frame_bytes = emulator.latest_jpeg_bytes
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n\r\n" +
                frame_bytes + b"\r\n"
            )
        await asyncio.sleep(1.0 / max(10, settings.target_fps))

@app.get("/stream")
async def video_stream():
    """Returns low-latency MJPEG video stream."""
    return StreamingResponse(
        frame_stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "rom": emulator.rom_name,
        "mode": game_mode.current_mode,
        "fps": emulator.fps_counter
    }

@app.get("/api/status")
async def api_status():
    return get_full_status()

class ManualInputModel(BaseModel):
    command: str
    user: str = "REST_User"

@app.post("/api/input")
async def api_input(body: ManualInputModel):
    handle_user_command(body.user, body.command, source="api")
    return {"status": "ok", "received": body.command}

@app.post("/api/save")
async def api_save():
    success = emulator.save_state()
    return {"status": "saved" if success else "failed"}

# --- ADMIN API ---
class AdminVerifyModel(BaseModel):
    password: str

class AdminActionModel(BaseModel):
    action: str
    data: Optional[Any] = None

@app.post("/api/admin/verify")
async def api_admin_verify(body: AdminVerifyModel):
    if not admin_manager.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Falsches Admin-Passwort")
    return {
        "status": "ok",
        "settings": admin_manager.config.model_dump(),
        "actual_rom": emulator.rom_name,
        "available_roms": emulator.list_available_roms(),
        "queue_size": anarchy_queue.qsize()
    }

@app.get("/api/admin/settings")
async def api_admin_get_settings(x_admin_password: Optional[str] = Header(None)):
    if not admin_manager.verify_password(x_admin_password):
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    return {
        "settings": admin_manager.config.model_dump(),
        "actual_rom": emulator.rom_name,
        "available_roms": emulator.list_available_roms(),
        "queue_size": anarchy_queue.qsize(),
        "fps": emulator.fps_counter
    }

@app.post("/api/admin/settings")
async def api_admin_update_settings(updates: Dict[str, Any], x_admin_password: Optional[str] = Header(None)):
    if not admin_manager.verify_password(x_admin_password):
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    new_cfg = admin_manager.update_settings(updates, game_mode, emulator)
    await broadcast_ws({
        "type": "status_update",
        "status": get_full_status()
    })
    return {"status": "ok", "settings": new_cfg}

@app.post("/api/admin/action")
async def api_admin_action(body: AdminActionModel, x_admin_password: Optional[str] = Header(None)):
    if not admin_manager.verify_password(x_admin_password):
        raise HTTPException(status_code=401, detail="Nicht autorisiert")

    act = body.action
    if act == "clear_queue":
        count = clear_anarchy_queue()
        await broadcast_ws({
            "type": "system_announcement",
            "text": "Warteschlange wurde vom Admin geleert."
        })
        await broadcast_ws({
            "type": "status_update",
            "status": get_full_status()
        })
        return {"status": "ok", "cleared": count}

    elif act == "save_state":
        success = emulator.save_state()
        return {"status": "saved" if success else "failed"}

    elif act == "load_state":
        success = emulator.load_state()
        if success:
            await broadcast_ws({
                "type": "system_announcement",
                "text": "Letzter Speicherstand wurde vom Admin geladen."
            })
            await broadcast_ws({
                "type": "status_update",
                "status": get_full_status()
            })
        return {"status": "loaded" if success else "failed"}

    elif act == "switch_rom":
        rom_name = str(body.data or "").strip()
        if not rom_name:
            raise HTTPException(status_code=400, detail="Keine ROM ausgewählt")
        success = emulator.switch_rom(rom_name)
        if success:
            admin_manager.config.selected_rom = rom_name
            admin_manager.save()
            clear_anarchy_queue()
            await broadcast_ws({
                "type": "system_announcement",
                "text": f"🎮 Spiel gewechselt zu: {rom_name}!"
            })
            await broadcast_ws({
                "type": "status_update",
                "status": get_full_status()
            })
            return {
                "status": "ok",
                "rom": rom_name,
                "available_roms": emulator.list_available_roms()
            }
        else:
            raise HTTPException(status_code=400, detail=f"ROM '{rom_name}' konnte nicht gestartet werden")

    elif act == "announcement":
        msg = str(body.data or "").strip()
        if msg:
            await broadcast_ws({
                "type": "system_announcement",
                "text": f"[Admin] {msg}"
            })
        return {"status": "ok"}

    raise HTTPException(status_code=400, detail="Unbekannte Aktion")

@app.post("/api/admin/upload_rom")
async def api_admin_upload_rom(
    request: Request,
    x_rom_filename: Optional[str] = Header(None),
    x_admin_password: Optional[str] = Header(None)
):
    if not admin_manager.verify_password(x_admin_password):
        raise HTTPException(status_code=401, detail="Nicht autorisiert")

    if not x_rom_filename:
        raise HTTPException(status_code=400, detail="Kein Dateiname angegeben (Header X-ROM-Filename fehlt)")

    raw_filename = unquote(x_rom_filename)
    base_name = Path(raw_filename).name
    clean_name = re.sub(r'[^a-zA-Z0-9_\-\. ]', '_', base_name).strip()
    clean_name = clean_name.replace(" ", "_")

    suffix = Path(clean_name).suffix.lower()
    if suffix not in (".gb", ".gbc"):
        raise HTTPException(status_code=400, detail="Nur .gb und .gbc Game Boy ROMs sind erlaubt!")

    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Die Datei ist leer.")

    if len(content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Datei ist zu groß (maximal 16 MB)")
    if len(content) < 32 * 1024:
        raise HTTPException(status_code=400, detail="Datei ist zu klein für eine gültige ROM (mind. 32 KB)")

    rom_dir = Path(settings.rom_dir)
    rom_dir.mkdir(parents=True, exist_ok=True)
    target_path = rom_dir / clean_name

    with open(target_path, "wb") as f:
        f.write(content)

    try:
        target_path.chmod(0o666)
    except Exception:
        pass

    logger.info(f"ROM '{clean_name}' successfully uploaded via Drag & Drop ({len(content)} bytes)")

    return {
        "status": "ok",
        "filename": clean_name,
        "size": len(content),
        "available_roms": emulator.list_available_roms(),
        "actual_rom": emulator.rom_name
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.add(websocket)
    
    # Send initial state snapshot
    await websocket.send_json({
        "type": "init",
        "status": get_full_status()
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "command")
            user = data.get("user", "Anonymous").strip() or "Anonymous"
            text = data.get("text", "").strip()

            if msg_type in ("command", "chat") and text:
                # Broadcast chat message to all viewers
                await broadcast_ws({
                    "type": "chat_message",
                    "user": user,
                    "text": text,
                    "time": time.strftime("%H:%M:%S")
                })
                # Check if it triggers a game command
                handle_user_command(user, text, source="web")
    except WebSocketDisconnect:
        pass
    finally:
        connected_websockets.discard(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info"
    )
