import os
import asyncio
import logging
from pyrogram import Client, filters, __version__
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated
from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, AUTO_DELETE_MSG
from helper_func import subscribed, encode, decode, get_messages
from database.database import add_user, del_user, full_userbase, present_user
from plugins.FORCESUB import f_invitelink

# Setting up the logger
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Single /start handler for the bot
@Bot.on_message(filters.command('start') & filters.private)
async def start_command(client: Client, message: Message):
    logger.debug("Start command received")
    id = message.from_user.id
    logger.debug(f"User ID: {id}")

    if not await present_user(id):
        try:
            logger.info(f"User {id} not found in database. Adding user.")
            await add_user(id)
        except Exception as e:
            logger.error(f"Error adding user {id}: {e}")

    text = message.text
    logger.debug(f"Received message text: {text}")

    if len(text) > 7:
        try:
            base64_string = text.split(" ", 1)[1]
            logger.debug(f"Base64 string extracted: {base64_string}")
        except IndexError:
            logger.warning("Base64 string extraction failed.")
            return

        string = await decode(base64_string)
        logger.debug(f"Decoded string: {string}")
        argument = string.split("-")
        logger.debug(f"Decoded arguments: {argument}")

        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
                logger.debug(f"Start range: {start}, End range: {end}")
            except Exception as e:
                logger.error(f"Error parsing range arguments: {e}")
                return
            ids = range(start, end + 1) if start <= end else [i for i in range(start, end - 1, -1)]
            logger.debug(f"Generated ID range: {ids}")
        elif len(argument) == 2:
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
                logger.debug(f"Single ID extracted: {ids}")
            except Exception as e:
                logger.error(f"Error parsing single ID: {e}")
                return

        temp_msg = await message.reply("Please wait...")
        try:
            logger.info("Fetching messages...")
            messages = await get_messages(client, ids)
            logger.info(f"Fetched {len(messages)} messages.")
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            await message.reply_text("Something went wrong..!")
            return
        await temp_msg.delete()

        track_msgs = []  # Initialize tracking list
        for msg in messages:
            try:
                logger.debug(f"Processing message ID {msg.message_id}")
                caption = CUSTOM_CAPTION.format(previouscaption="" if not msg.caption else msg.caption.html, filename=msg.document.file_name) if CUSTOM_CAPTION and msg.document else "" if not msg.caption else msg.caption.html
                reply_markup = msg.reply_markup if not DISABLE_CHANNEL_BUTTON else None
                logger.debug(f"Caption prepared: {caption}")

                if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                    try:
                        logger.debug(f"Copying message for auto-deletion with caption: {caption}")
                        copied_msg_for_deletion = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                        if copied_msg_for_deletion:
                            logger.info(f"Message {msg.message_id} copied successfully.")
                            track_msgs.append(copied_msg_for_deletion)
                        else:
                            logger.warning(f"Failed to copy message {msg.message_id}, skipping.")
                    except FloodWait as e:
                        logger.warning(f"FloodWait encountered: {e.value} seconds. Retrying...")
                        await asyncio.sleep(e.value)
                        copied_msg_for_deletion = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                        if copied_msg_for_deletion:
                            logger.info(f"Message {msg.message_id} copied successfully after retry.")
                            track_msgs.append(copied_msg_for_deletion)
                        else:
                            logger.warning(f"Failed to copy message {msg.message_id} after retry, skipping.")
                    except Exception as e:
                        logger.error(f"Error copying message {msg.message_id}: {e}")
                        pass
                else:
                    try:
                        logger.debug(f"Copying message without auto-deletion with caption: {caption}")
                        await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                        logger.info(f"Message {msg.message_id} copied successfully without auto-deletion.")
                        await asyncio.sleep(0.5)
                    except FloodWait as e:
                        logger.warning(f"FloodWait encountered: {e.x} seconds. Retrying...")
                        await asyncio.sleep(e.x)
                        await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                    except Exception as e:
                        logger.error(f"Error copying message {msg.message_id}: {e}")
                        pass

        if track_msgs:
            try:
                logger.info("Sending auto-delete message to user.")
                delete_data = await client.send_message(
                    chat_id=message.from_user.id,
                    text=AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
                )
                asyncio.create_task(delete_file(track_msgs, client, delete_data))
            except Exception as e:
                logger.error(f"Error sending auto-delete message: {e}")
        else:
            logger.info("No messages to track for deletion.")

    reply_markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("😊 About Me", callback_data="about"),
                InlineKeyboardButton("🔒 Close", callback_data="close"),
            ]
        ]
    )
    if START_PIC:
        try:
            logger.debug("Sending start photo with caption.")
            await message.reply_photo(
                photo=START_PIC,
                caption=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                quote=True
            )
        except Exception as e:
            logger.error(f"Error sending start photo: {e}")
    else:
        try:
            logger.debug("Sending start text message.")
            await message.reply_text(
                text=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                quote=True
            )
        except Exception as e:
            logger.error(f"Error sending start text message: {e}")


#=====================================================================================##

WAIT_MSG = """<b>Processing ...</b>"""

REPLY_ERROR = """<code>Use this command as a reply to any telegram message without any spaces.</code>"""

#=====================================================================================##

@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    logger.info(f"Received '/start' command from {message.from_user.id}")
    
    buttons = [
        [
            InlineKeyboardButton(text="Join Channel", url=f_invitelink if 'f_invitelink' in globals() else client.invitelink),
            InlineKeyboardButton(text="Join Channel", url=client.invitelink2),
        ],
        [
            InlineKeyboardButton(text="Join Channel", url=client.invitelink3),
            InlineKeyboardButton(text="Join Channel", url=client.invitelink4),
        ]
    ]
    try:
        buttons.append(
            [
                InlineKeyboardButton(
                    text='Try Again',
                    url=f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ]
        )
    except IndexError:
        logger.warning(f"Failed to append 'Try Again' button due to missing command argument.")

    try:
        await message.reply(
            text=FORCE_MSG.format(
                first=message.from_user.first_name,
                last=message.from_user.last_name,
                username=None if not message.from_user.username else '@' + message.from_user.username,
                mention=message.from_user.mention,
                id=message.from_user.id
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True,
            disable_web_page_preview=True
        )
        logger.info(f"Replied to user {message.from_user.id} with start message.")
    except Exception as e:
        logger.error(f"Failed to send message to user {message.from_user.id}: {e}")

@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    logger.info(f"Received '/users' command from admin {message.from_user.id}")
    try:
        msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
        users = await full_userbase()
        await msg.edit(f"{len(users)} users are using this bot")
        logger.info(f"Sent user count to admin {message.from_user.id}")
    except Exception as e:
        logger.error(f"Failed to retrieve or display user count: {e}")

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    logger.info(f"Received '/broadcast' command from admin {message.from_user.id}")
    
    if message.reply_to_message:
        try:
            query = await full_userbase()
            broadcast_msg = message.reply_to_message
            total = 0
            successful = 0
            blocked = 0
            deleted = 0
            unsuccessful = 0
            
            pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
            logger.info("Starting broadcast to users...")
            
            for chat_id in query:
                try:
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                    logger.info(f"Message successfully sent to {chat_id}")
                except FloodWait as e:
                    logger.warning(f"Rate limit hit for {chat_id}, sleeping for {e.x} seconds")
                    await asyncio.sleep(e.x)
                    await broadcast_msg.copy(chat_id)
                    successful += 1
                except UserIsBlocked:
                    await del_user(chat_id)
                    blocked += 1
                    logger.info(f"User {chat_id} blocked the bot")
                except InputUserDeactivated:
                    await del_user(chat_id)
                    deleted += 1
                    logger.info(f"User {chat_id} has deleted their account")
                except Exception as e:
                    unsuccessful += 1
                    logger.error(f"Failed to send message to {chat_id}: {e}")
                total += 1
            
            status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
            
            logger.info("Broadcast completed successfully.")
            await pls_wait.edit(status)
        
        except Exception as e:
            logger.error(f"Error occurred during broadcasting: {e}")
            await message.reply(REPLY_ERROR)
            await asyncio.sleep(8)
            await message.delete()
    else:
        msg = await message.reply(REPLY_ERROR)
        logger.info(f"User {message.from_user.id} did not reply to a message for broadcast")
        await asyncio.sleep(8)
        await msg.delete()
