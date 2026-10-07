import asyncio
import logging
import random
import re
from typing import Callable, Optional

logger = logging.getLogger("twitch_bot")

PRIVMSG_REGEX = re.compile(r"^:([a-zA-Z0-9_]+)![a-zA-Z0-9_]+@[a-zA-Z0-9_.]+\.tmi\.twitch\.tv PRIVMSG #[a-zA-Z0-9_]+ :(.*)$")

class TwitchBot:
    def __init__(
        self,
        channel: str,
        oauth_token: str = "",
        nickname: str = "",
        on_message_callback: Optional[Callable[[str, str], None]] = None
    ):
        self.channel = channel.lower().lstrip("#")
        self.oauth_token = oauth_token.strip()
        self.nickname = nickname.strip() or f"justinfan{random.randint(10000, 99999)}"
        self.on_message_callback = on_message_callback
        
        self.is_running = False
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None

    async def start(self):
        """Starts the Twitch IRC connection loop with automatic reconnect."""
        if not self.channel:
            logger.info("No Twitch channel configured. Twitch IRC client disabled.")
            return

        self.is_running = True
        logger.info(f"Connecting to Twitch IRC for channel #{self.channel} as {self.nickname}...")

        backoff = 2
        while self.is_running:
            try:
                await self._connect_and_listen()
                backoff = 2
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Twitch IRC connection dropped ({e}). Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _connect_and_listen(self):
        self.reader, self.writer = await asyncio.open_connection("irc.chat.twitch.tv", 6667)
        
        # Send authentication / handshake
        if self.oauth_token:
            token = self.oauth_token if self.oauth_token.startswith("oauth:") else f"oauth:{self.oauth_token}"
            self.writer.write(f"PASS {token}\r\n".encode())
        else:
            self.writer.write(b"PASS SCHMENDRIK\r\n")

        self.writer.write(f"NICK {self.nickname}\r\n".encode())
        self.writer.write(f"JOIN #{self.channel}\r\n".encode())
        await self.writer.drain()

        logger.info(f"Joined Twitch chat: #{self.channel}")

        while self.is_running:
            line_bytes = await self.reader.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Respond to keep-alive PING
            if line.startswith("PING"):
                pong_reply = line.replace("PING", "PONG")
                self.writer.write(f"{pong_reply}\r\n".encode())
                await self.writer.drain()
                continue

            # Parse chat messages
            match = PRIVMSG_REGEX.match(line)
            if match:
                user = match.group(1)
                text = match.group(2).strip()
                if self.on_message_callback:
                    try:
                        self.on_message_callback(user, text)
                    except Exception as err:
                        logger.error(f"Error executing message callback: {err}")

    async def stop(self):
        self.is_running = False
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        logger.info("Twitch IRC connection closed.")
