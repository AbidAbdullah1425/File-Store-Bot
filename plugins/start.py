import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from bot import Bot
from config import (
    ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON,
    PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, AUTO_DELETE_MSG
)
from helper_func import subscribed, encode, decode, get_messages
from database.database import add_user, del_user, full_userbase, present_user
from plugins.FORCESUB import f_invitelink

# Set up the logger
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    logger.debug("Start command received")
    user_id = message.from_user.id

    if not await present_user(user_id):
        try:
            logger.info(f"Adding new user {user_id} to the database.")
            await add_user(user_id)
        except Exception as e:
            logger.error(f"Failed to add user {user_id}: {e}")

    if len(message.text) > 7:
        try:
            base64_string = message.text.split(" ", 1)[1]
            decoded_string = await decode(base64_string)
            args = decoded_string.split("-")

            if len(args) == 3:
                start, end = map(lambda x: int(int(x) / abs(client.db_channel.id)), args[1:])
                ids = range(start, end + 1) if start <= end else range(start, end - 1, -1)
            elif len(args) == 2:
                ids = [int(int(args[1]) / abs(client.db_channel.id))]
            else:
                ids = []

            temp_msg = await message.reply("Fetching messages...")
            try:
                messages = await get_messages(client, ids)
            except Exception as e:
                logger.error(f"Failed to fetch messages: {e}")
                await message.reply_text("Failed to fetch messages.")
                return
            await temp_msg.delete()

            track_msgs = []
            for msg in messages:
                try:
                    caption = CUSTOM_CAPTION.format(
                        previouscaption=msg.caption.html if msg.caption else "",
                        filename=msg.document.file_name
                    ) if CUSTOM_CAPTION and msg.document else msg.caption.html if msg.caption else ""

                    reply_markup = None if DISABLE_CHANNEL_BUTTON else msg.reply_markup

                    if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                        copied_msg = await msg.copy(
                            chat_id=message.from_user.id,
                            caption=caption,
                            reply_markup=reply_markup,
                            protect_content=PROTECT_CONTENT
                        )
                        track_msgs.append(copied_msg)
                    else:
                        await msg.copy(
                            chat_id=message.from_user.id,
                            caption=caption,
                            reply_markup=reply_markup,
                            protect_content=PROTECT_CONTENT
                        )
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    continue
                except Exception as e:
                    logger.error(f"Error processing message {msg.message_id}: {e}")
                    continue

            if track_msgs:
                await client.send_message(
                    chat_id=message.from_user.id,
                    text=AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
                )
                asyncio.create_task(delete_file(track_msgs, client))
        except Exception as e:
            logger.error(f"Error handling /start argument: {e}")
    else:
        try:
            reply_markup = InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("😊 About Me", callback_data="about"),
                    InlineKeyboardButton("🔒 Close", callback_data="close"),
                ]]
            )
            if START_PIC:
                await message.reply_photo(
                    photo=START_PIC,
                    caption=START_MSG.format(
                        first=message.from_user.first_name,
                        last=message.from_user.last_name,
                        username=message.from_user.username,
                        mention=message.from_user.mention,
                        id=message.from_user.id
                    ),
                    reply_markup=reply_markup
                )
            else:
                await message.reply_text(
                    text=START_MSG.format(
                        first=message.from_user.first_name,
                        last=message.from_user.last_name,
                        username=message.from_user.username,
                        mention=message.from_user.mention,
                        id=message.from_user.id
                    ),
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Failed to send start message: {e}")


@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    try:
        msg = await client.send_message(chat_id=message.chat.id, text="Processing...")
        users = await full_userbase()
        await msg.edit(f"{len(users)} users are using this bot.")
    except Exception as e:
        logger.error(f"Error retrieving user list: {e}")


@Bot.on_message(filters.command('broadcast') & filters.private & filters.user(ADMINS))
async def broadcast_message(client: Bot, message: Message):
    if message.reply_to_message:
        try:
            users = await full_userbase()
            msg = await message.reply("Broadcasting...")

            successful, blocked, deleted, failed = 0, 0, 0, 0
            for user_id in users:
                try:
                    await message.reply_to_message.copy(chat_id=user_id)
                    successful += 1
                except UserIsBlocked:
                    await del_user(user_id)
                    blocked += 1
                except InputUserDeactivated:
                    await del_user(user_id)
                    deleted += 1
                except Exception as e:
                    failed += 1
                    logger.error(f"Failed to send message to {user_id}: {e}")

            await msg.edit(f"Broadcast completed: {successful} successful, {blocked} blocked, {deleted} deleted, {failed} failed.")
        except Exception as e:
            logger.error(f"Error during broadcast: {e}")
    else:
        await message.reply("Reply to a message to broadcast.")


async def delete_file(track_msgs, client):
    await asyncio.sleep(AUTO_DELETE_TIME)
    for msg in track_msgs:
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=msg.message_id)
        except Exception as e:
            logger.error(f"Failed to delete message {msg.message_id}: {e}")
