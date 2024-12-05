
import os
import sys
from pyrogram import Client, filters
from config import OWNER_ID
from bot import Bot

#Restart to cancell all process 
@Bot.on_message(filters.private & filters.command("restart") & filters.user(OWNER_ID))
async def restart_bot(b, m):
    await m.reply_text("💫__Rᴇꜱᴛᴀʀᴛɪɴɢ.....__")
    os.execl(sys.executable, sys.executable, *sys.argv)