# --| Created by: Jisshu_bots & SilentXBotz |-- Modified by: ChatGPT AI ✨

import re, hashlib, asyncio, aiohttp
from collections import defaultdict
from typing import Optional

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id
from info import *
from utils import *

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam",
    "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish",
    "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu"
]

UPDATE_CAPTION = """
📫 <b>নতুন ফাইল যুক্ত হয়েছে ✅</b>

🚧 <b>শিরোনাম:</b> {}
🎧 <b>ভাষা:</b> {}
🔖 <b>ধরন:</b> {}

🚀 <b>টেলিগ্রাম ফাইল:</b> ✨
{}

〽️ <i>Powered by</i> @RM_Movie_Flix
"""

QUALITY_CAPTION = "📦 <b>#{}:</b> {}\n"

# Runtime data
notified_movies = set()
movie_files = defaultdict(list)
processing_movies = set()
POST_DELAY = 10

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media_handler(bot, message):
    bot_id = bot.me.id
    media = getattr(message, message.media.value, None)
    if not media or media.mime_type not in ['video/mp4', 'video/x-matroska', 'application/octet-stream']:
        return

    media.file_type = message.media.value
    media.caption = message.caption

    if await save_file(media) == 'suc' and await db.get_send_movie_update_status(bot_id):
        await queue_movie_file(bot, media)


async def queue_movie_file(bot, media):
    try:
        caption = await movie_name_format(media.caption or "")
        file_name = await movie_name_format(media.file_name or "")
        year = re.search(r"\b(19|20)\d{2}\b", caption)
        season = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption or file_name)

        if year:
            file_name = file_name[:file_name.find(year.group()) + 4]
        elif season:
            file_name = file_name[:file_name.find(season.group(1)) + 1]

        quality = await get_qualities(caption) or "HDRip"
        jisshu_quality = await Jisshu_qualities(caption, media.file_name) or "720p"
        language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Found"
        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        movie_files[file_name].append({
            "quality": quality,
            "jisshuquality": jisshu_quality,
            "file_id": file_id,
            "file_size": file_size_str,
            "caption": caption,
            "language": language,
            "year": year.group() if year else None
        })

        if file_name in processing_movies:
            return
        processing_movies.add(file_name)

        await asyncio.sleep(POST_DELAY)

        if file_name in movie_files:
            await send_movie_update(bot, file_name, movie_files[file_name])
            del movie_files[file_name]

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"⚠️ Movie queue error:\n<code>{e}</code>")
    finally:
        processing_movies.discard(file_name)


async def send_movie_update(bot, file_name, files):
    try:
        if file_name in notified_movies:
            return

        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name)
        kind = imdb_data.get("kind", "Movie").upper()
        poster = await fetch_movie_poster(title, files[0].get("year"))

        languages = sorted({lang for file in files if file["language"] != "Not Found"
                            for lang in file["language"].split(", ")})
        language = ", ".join(languages) or "Not Found"

        quality_groups = defaultdict(list)
        for file in files:
            quality_groups[file["jisshuquality"]].append(file)

        quality_links = []
        for q in sorted(quality_groups.keys()):
            links = [f"<a href='https://t.me/{temp.U_NAME}?start=file_0{f['file_id']}'>{f['file_size']}</a>"
                     for f in quality_groups[q]]
            quality_links.append(QUALITY_CAPTION.format(q, " | ".join(links)))

        full_caption = UPDATE_CAPTION.format(title, language, kind, "\n".join(quality_links))
        image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        search_movie = title.replace(" ", "-")

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get All Files", url=f"https://t.me/{temp.U_NAME}?start=getfile-{search_movie}")],
            [InlineKeyboardButton("🎥 Movie Request Group", url="https://t.me/Movies_Rm")]
        ])

        update_channel = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL

        await bot.send_photo(
            chat_id=update_channel,
            photo=image_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons
        )
        notified_movies.add(file_name)

    except Exception as e:
        await bot.send_message(LOG_CHANNEL, f"🚨 Failed to send movie update.\n<code>{e}</code>")


async def get_imdb(file_name):
    try:
        name = await movie_name_format(file_name)
        imdb = await get_poster(name)
        return {
            "title": imdb.get("title", name),
            "kind": imdb.get("kind", "Movie"),
            "year": imdb.get("year"),
            "url": imdb.get("url")
        } if imdb else {}
    except Exception as e:
        print(f"[IMDb Error] {e}")
        return {}


async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        url = f"https://jisshuapis.vercel.app/api.php?query={title.replace(' ', '+')}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
        except Exception as e:
            print(f"[Poster API] Error: {e}")
        return None


async def get_qualities(text):
    qualities = [
        "480p", "720p", "720p HEVC", "1080p", "ORG", "hdcam", "HQ", "HDRip", "camrip",
        "WEB-DL", "hdtc", "predvd", "DVDscr", "dvdscr", "dvdrip", "HDTC", "dvdscreen", "HDTS"
    ]
    return ", ".join([q for q in qualities if q.lower() in text.lower()]) or "HDRip"


async def Jisshu_qualities(text, file_name):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    combined = (text + " " + file_name).lower()
    if "hevc" in combined:
        return next((q for q in qualities if "HEVC" in q and q.split()[0].lower() in combined), "720p")
    return next((q for q in qualities if "HEVC" not in q and q.lower() in combined), "720p")


async def movie_name_format(name):
    return re.sub(r'[^\w\s]', '', re.sub(r'http\S+|@\w+|#\w+', '', name))\
        .replace('_', ' ').replace('.', ' ').strip()


def format_file_size(size_bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"
