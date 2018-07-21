import base64
import binascii
import logging
import re
import struct
from datetime import datetime

from discord import Message
from discord.ext.commands import Bot
from discord.utils import snowflake_time

from bot.constants import Channels


log = logging.getLogger(__name__)

DELETION_MESSAGE_TEMPLATE = (
    "Hey {mention}! I noticed you posted a seemingly valid Discord API "
    "token in your message and have removed your message to prevent abuse. "
    "We recommend regenerating your token regardless, which you can do here: "
    "<https://discordapp.com/developers/applications/me>\n"
    "Feel free to re-post it with the token removed. "
    "If you believe this was a mistake, please let us know!"
)
DISCORD_EPOCH_TIMESTAMP = datetime(2017, 1, 1)
TOKEN_EPOCH = 1_293_840_000
TOKEN_RE = re.compile(
    r"(?<=(\"|'))"  # Lookbehind: Only match if there's a double or single quote in front
    r"[^\W\.]+"  # Matches token part 1: The user ID string, encoded as base64
    r"\."  # Matches a literal dot between the token parts
    r"[^\W\.]+"  # Matches token part 2: The creation timestamp, as an integer
    r"\."  # Matches a literal dot between the token parts
    r"[^\W\.]+"  # Matches token part 3: The HMAC, unused by us, but check that it isn't empty
    r"(?=(\"|'))"  # Lookahead: Only match if there's a double or single quote after
)


class TokenRemover:
    """Scans messages for potential discord.py bot tokens and removes them."""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.modlog = None

    async def on_ready(self):
        self.modlog = self.bot.get_channel(Channels.modlog)

    async def on_message(self, msg: Message):
        if msg.author.bot:
            return

        maybe_match = TOKEN_RE.search(msg.content)
        if maybe_match is None:
            return

        try:
            user_id, creation_timestamp, hmac = maybe_match.group(0).split('.')
        except ValueError:
            return

        if self.is_valid_user_id(user_id) and self.is_valid_timestamp(creation_timestamp):
            await msg.delete()
            await msg.channel.send(DELETION_MESSAGE_TEMPLATE.format(mention=msg.author.mention))
            await self.modlog.send(
                ":key2::mute: censored a seemingly valid token sent by "
                f"{msg.author} (`{msg.author.id}`) in {msg.channel.mention}, token was "
                f"`{user_id}.{creation_timestamp}.{'x' * len(hmac)}`"
            )

    @staticmethod
    def is_valid_user_id(b64_content: str) -> bool:
        b64_content += '=' * (-len(b64_content) % 4)

        try:
            content: bytes = base64.b64decode(b64_content)
            return content.decode('utf-8').isnumeric()
        except (binascii.Error, UnicodeDecodeError):
            return False

    @staticmethod
    def is_valid_timestamp(b64_content: str) -> bool:
        b64_content += '=' * (-len(b64_content) % 4)

        try:
            content = base64.urlsafe_b64decode(b64_content)
            snowflake = struct.unpack('i', content)[0]
        except (binascii.Error, struct.error):
            return False
        return snowflake_time(snowflake + TOKEN_EPOCH) < DISCORD_EPOCH_TIMESTAMP


def setup(bot: Bot):
    bot.add_cog(TokenRemover(bot))
    log.info("Cog loaded: TokenRemover")