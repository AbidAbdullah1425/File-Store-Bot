import base64
import re
import asyncio
import logging
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors.exceptions.bad_request_400 import UserNotParticipant
from pyrogram.errors import FloodWait
from database.database import get_force_sub_channel  # Import the MongoDB function
from config import FORCE_SUB_CHANNEL_1, FORCE_SUB_CHANNEL_2, FORCE_SUB_CHANNEL_3, FORCE_SUB_CHANNEL_4, ADMINS, AUTO_DELETE_TIME, AUTO_DEL_SUCCESS_MSG

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

async def is_subscribed(filter, client, update):
    logger.debug(f"Checking subscription for user ID: {update.from_user.id}")
    try:
        force_sub_channel = get_force_sub_channel("FORCE_SUB_CHANNEL_1")
        logger.debug(f"Retrieved force subscription channel from MongoDB: {force_sub_channel}")
    except Exception as e:
        logger.error(f"Error retrieving channel from MongoDB: {e}")
        force_sub_channel = None

    if not force_sub_channel:
        logger.warning("No channel found in MongoDB. Falling back to config.py")
        force_sub_channel = FORCE_SUB_CHANNEL_1

    if not force_sub_channel:
        logger.error("No valid channel ID found. Skipping subscription check.")
        return True

    user_id = update.from_user.id

    if user_id in ADMINS:
        logger.info(f"User ID {user_id} is an admin. Bypassing subscription check.")
        return True

    allowed_statuses = {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}

    try:
        member = await client.get_chat_member(chat_id=force_sub_channel, user_id=user_id)
        logger.debug(f"User membership status: {member.status}")
        if member.status not in allowed_statuses:
            logger.warning(f"User ID {user_id} is not subscribed to {force_sub_channel}")
            return False
    except UserNotParticipant:
        logger.warning(f"User ID {user_id} is not a participant in {force_sub_channel}")
        return False
    except FloodWait as e:
        logger.error(f"FloodWait error: Waiting for {e.value} seconds")
        await asyncio.sleep(e.value)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during subscription check: {e}")
        return False

    logger.info(f"User ID {user_id} is subscribed to {force_sub_channel}")
    return True

async def encode(string):
    logger.debug(f"Encoding string: {string}")
    string_bytes = string.encode("ascii")
    base64_bytes = base64.urlsafe_b64encode(string_bytes)
    base64_string = (base64_bytes.decode("ascii")).strip("=")
    logger.debug(f"Encoded string: {base64_string}")
    return base64_string

async def decode(base64_string):
    logger.debug(f"Decoding base64 string: {base64_string}")
    base64_string = base64_string.strip("=")
    base64_bytes = (base64_string + "=" * (-len(base64_string) % 4)).encode("ascii")
    string_bytes = base64.urlsafe_b64decode(base64_bytes)
    decoded_string = string_bytes.decode("ascii")
    logger.debug(f"Decoded string: {decoded_string}")
    return decoded_string

async def get_messages(client, message_ids):
    logger.debug(f"Fetching messages for IDs: {message_ids}")
    messages = []
    total_messages = 0
    while total_messages != len(message_ids):
        temp_ids = message_ids[total_messages:total_messages+200]
        try:
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temp_ids
            )
        except FloodWait as e:
            logger.warning(f"FloodWait error: Waiting for {e.x} seconds")
            await asyncio.sleep(e.x)
            msgs = await client.get_messages(
                chat_id=client.db_channel.id,
                message_ids=temp_ids
            )
        except Exception as e:
            logger.error(f"Error fetching messages: {e}")
            msgs = []
        total_messages += len(temp_ids)
        messages.extend(msgs)
    logger.debug(f"Retrieved messages: {len(messages)}")
    return messages

async def get_message_id(client, message):
    logger.debug(f"Extracting message ID from message: {message}")
    try:
        if message.forward_from_chat:
            if message.forward_from_chat.id == client.db_channel.id:
                return message.forward_from_message_id
            else:
                return 0
        elif message.forward_sender_name:
            return 0
        elif message.text:
            pattern = "https://t.me/(?:c/)?(.*)/(\d+)"
            matches = re.match(pattern, message.text)
            if not matches:
                return 0
            channel_id = matches.group(1)
            msg_id = int(matches.group(2))
            if channel_id.isdigit():
                if f"-100{channel_id}" == str(client.db_channel.id):
                    return msg_id
            else:
                if channel_id == client.db_channel.username:
                    return msg_id
        else:
            return 0
    except Exception as e:
        logger.error(f"Error extracting message ID: {e}")
        return 0

def get_readable_time(seconds: int) -> str:
    logger.debug(f"Converting seconds ({seconds}) to readable time.")
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    hmm = len(time_list)
    for x in range(hmm):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += f"{time_list.pop()}, "
    time_list.reverse()
    up_time += ":".join(time_list)
    logger.debug(f"Readable time: {up_time}")
    return up_time

async def delete_file(messages, client, process):
    logger.debug(f"Deleting files: {messages}")
    await asyncio.sleep(AUTO_DELETE_TIME)
    for msg in messages:
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=[msg.id])
        except Exception as e:
            await asyncio.sleep(e.x)
            logger.error(f"The attempt to delete the media {msg.id} was unsuccessful: {e}")

    await process.edit_text(AUTO_DEL_SUCCESS_MSG)

subscribed = filters.create(is_subscribed)
