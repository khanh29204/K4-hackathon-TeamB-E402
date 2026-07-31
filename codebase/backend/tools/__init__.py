from __future__ import annotations

from .clarify.tool import ask_user
from .current_time.tool import get_current_time
from .format.tool import render_digest
from .gmail_search.tool import gmail_search
from .gmail_read_thread.tool import gmail_read_thread
from .discord_find_channel.tool import discord_find_channel
from .discord_read_messages.tool import discord_read_messages
from .discord_list_guilds.tool import discord_list_guilds
from .discord_server_info.tool import discord_server_info
from .discord_list_channels.tool import discord_list_channels
from .calendar_list_events.tool import calendar_list_events
from .calendar_create_event.tool import calendar_create_event
from .outlook_mail_search.tool import outlook_mail_search
from .outlook_mail_read.tool import outlook_mail_read
from .outlook_calendar_list_events.tool import outlook_calendar_list_events

TOOL_FUNCTIONS = {
    "clarify": ask_user,
    "current_time": get_current_time,
    "format": render_digest,
    "gmail_search": gmail_search,
    "gmail_read_thread": gmail_read_thread,
    "discord_find_channel": discord_find_channel,
    "discord_read_messages": discord_read_messages,
    "discord_list_guilds": discord_list_guilds,
    "discord_server_info": discord_server_info,
    "discord_list_channels": discord_list_channels,
    "calendar_list_events": calendar_list_events,
    "calendar_create_event": calendar_create_event,
    "outlook_mail_search": outlook_mail_search,
    "outlook_mail_read": outlook_mail_read,
    "outlook_calendar_list_events": outlook_calendar_list_events,
}
