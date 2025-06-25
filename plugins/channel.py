# --| Created by: Jisshu_bots & SilentXBotz | Enhanced by ChatGPT |--#
import re
import hashlib
import asyncio
from info import *
from utils import *
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id
import aiohttp
from typing import Optional
from collections import defaultdict

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam",
    "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish",
    "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu",
]

UPDATE_CAPTION_MOVIE = """<b><blockquote>📫 NEW MOVIE ADDED ✅</blockquote>

🚧 Title : {}
🎧 {}
🔖 {}
<blockquote>🚀 Telegram Files ✨</blockquote>

{}
<blockquote>〽️ Powered by @RM_Movie_Flix</b></blockquote>"""

UPDATE_CAPTION_SERIES = """<b><blockquote>📺 NEW SERIES ADDED ✅</blockquote>

🎬 Title : {}
📅 Season : {}
🎧 {}
<blockquote>📁 Episodes:</blockquote>

{}
<blockquote>〽️ Powered by @RM_Movie_Flix</b></blockquote>"""

QUALITY_CAPTION = "📦 {} : {}\n"

notified_movies = set()
movie_files = defaultdict(list)
POST_DELAY = 10
processing_movies = set()

media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    bot_id = bot.me.id
    media = getattr(message, message.media.value, None)
    if not media or media.mime_type not in ["video/mp4", "video/x-matroska", "document/mp4"]:
        return

    media.file_type = message.media.value
    media.caption = message.caption
    success_sts = await save_file(media)

    if success_sts == "suc" and await db.get_send_movie_update_status(bot_id):
        await queue_movie_file(bot, media)


def is_series(text):
    return bool(re.search(r"(?i)(s\d{1,2}e\d{1,2}|season\s*\d+|episode\s*\d+)", text))


async def queue_movie_file(bot, media):
    try:
        original_name = media.file_name or ""
        caption_text = media.caption or original_name
        formatted_name = await movie_name_format(caption_text)
        file_title = formatted_name.split(" ")[0:6]
        file_title = " ".join(file_title).strip()

        year_match = re.search(r"\b(19|20)\d{2}\b", caption_text)
        year = year_match.group(0) if year_match else None

        season_match = re.search(r"(?i)s(?:eason)?\s*(\d{1,2})", caption_text)
        season = season_match.group(1) if season_match else "1"

        episode_match = re.search(r"(?i)e(?:pisode)?\s*(\d{1,2})", caption_text)
        episode = episode_match.group(1) if episode_match else None

        quality = await get_qualities(caption_text) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption_text, original_name) or "720p"

        language = ", ".join(
            f"#{lang.strip()}" for lang in CAPTION_LANGUAGES if lang.lower() in caption_text.lower()
        ) or "#NotIdea"

        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        group_key = f"{file_title}_S{season}"

        movie_files[group_key].append({
            "quality": quality,
            "jisshuquality": jisshuquality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption_text,
            "language": language,
            "year": year,
            "season": season,
            "episode": episode,
            "title": file_title,
        })

        if group_key in processing_movies:
            return
        processing_movies.add(group_key)

        try:
            await asyncio.sleep(POST_DELAY)
            if group_key in movie_files:
                files = movie_files[group_key]
                if is_series(caption_text):
                    await send_series_update(bot, group_key, files)
                else:
                    await send_movie_update(bot, file_title, files)
                del movie_files[group_key]
        finally:
            processing_movies.remove(group_key)

    except Exception as e:
        print(f"Error in queue_movie_file: {e}")
        await bot.send_message(LOG_CHANNEL, f"Failed to send update. Error - {e}")


async def send_series_update(bot, group_key, files):
    try:
        title = files[0]['title']
        season = files[0].get("season", "1")
        language = files[0]["language"]
        links = []
        for f in sorted(files, key=lambda x: int(x["episode"] or 0)):
            ep = f"Ep {f['episode']}" if f['episode'] else "Unknown"
            links.append(f"📦 {ep}: <a href='https://t.me/{temp.U_NAME}?start=file_0_{f['file_id']}'>{f['file_size']}</a>")

        quality_text = "\n".join(links)
        poster = await fetch_movie_poster(title, files[0].get("year")) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        full_caption = UPDATE_CAPTION_SERIES.format(title, season, language, quality_text)

        buttons = [
            [InlineKeyboardButton("📥 Get All Episodes", url=f"https://t.me/{temp.U_NAME}?start=getfile-{title.replace(' ', '-')}")],
            [InlineKeyboardButton("🎥 Series Request Group", url="https://t.me/RM_Movie_Flix")]
        ]

        movie_update_channel = await db.movies_update_channel_id()
        await bot.send_photo(
            chat_id=movie_update_channel if movie_update_channel else MOVIE_UPDATE_CHANNEL,
            photo=poster,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        print(f"Series update error: {e}")
        await bot.send_message(LOG_CHANNEL, f"Failed to send series update. Error - {e}")
