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

UPDATE_CAPTION_SERIES = """<b><blockquote>📺 NEW SERIES EPISODES ✅</blockquote>

📌 Title : {}
🗂️ Season : {}
🌐 Language : {}

🎞️ Episodes:

{}

<blockquote>〽️ Powered by @RM_Movie_Flix</b></blockquote>"""

EPISODE_CAPTION = "📦 E{:02d}: {}"
QUALITY_CAPTION = "📦 {} : {}\n"

notified_movies = set()
movie_files = defaultdict(list)
series_files = defaultdict(lambda: defaultdict(dict))
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


async def queue_movie_file(bot, media):
    try:
        file_name = await movie_name_format(media.file_name)
        caption = await movie_name_format(media.caption or "")
        year_match = re.search(r"\b(19|20)\d{2}\b", caption)
        year = year_match.group(0) if year_match else None

        episode_match = re.search(r"(?i)S(\d{1,2})E(\d{1,2})", caption)
        is_series = bool(episode_match)

        season_num = episode_num = None
        if is_series:
            season_num = int(episode_match.group(1))
            episode_num = int(episode_match.group(2))

        quality = await get_qualities(caption) or "HDRip"
        jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"

        language = ", ".join(
            f"#{lang.strip()}" for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()
        ) or "#NotIdea"

        file_size_str = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)

        if is_series:
            series_title = re.sub(r"S\d{1,2}E\d{1,2}.*", "", file_name).strip()
            series_files[series_title][season_num][episode_num] = {
                "file_id": file_id,
                "file_size": file_size_str,
                "language": language,
                "quality": jisshuquality,
            }
            await asyncio.sleep(POST_DELAY)
            await send_series_update(bot, series_title, season_num)
        else:
            movie_files[file_name].append({
                "quality": quality,
                "jisshuquality": jisshuquality,
                "file_id": file_id,
                "file_size": file_size_str,
                "caption": caption,
                "language": language,
                "year": year,
            })

            if file_name in processing_movies:
                return
            processing_movies.add(file_name)

            try:
                await asyncio.sleep(POST_DELAY)
                if file_name in movie_files:
                    await send_movie_update(bot, file_name, movie_files[file_name])
                    del movie_files[file_name]
            finally:
                processing_movies.remove(file_name)

    except Exception as e:
        print(f"Error in queue_movie_file: {e}")
        await bot.send_message(LOG_CHANNEL, f"Failed to send update. Error - {e}")


async def send_movie_update(bot, file_name, files):
    try:
        if file_name in notified_movies:
            return
        notified_movies.add(file_name)

        title = file_name
        kind = "#Movie"
        year = files[0].get("year")

        poster = await fetch_movie_poster(title, year)
        language_set = set()

        for file in files:
            if file["language"] != "#NotIdea":
                language_set.update(file["language"].split(", "))

        language = ", ".join(sorted(language_set)) or "#NotIdea"

        quality_groups = defaultdict(list)
        for file in files:
            quality_groups[f"#{file['jisshuquality']}"].append(file)

        sorted_qualities = sorted(quality_groups.keys())
        quality_links = []

        for quality in sorted_qualities:
            quality_files = quality_groups[quality]
            file_links = [
                f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{file['file_id']}'>{file['file_size']}</a>"
                for file in quality_files
            ]
            quality_links.append(QUALITY_CAPTION.format(quality, " | ".join(file_links)))

        quality_text = "\n".join(quality_links)
        image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        full_caption = UPDATE_CAPTION_MOVIE.format(title, language, kind, quality_text)

        search_movie = title.replace(" ", "-")
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get All Files", url=f"https://t.me/{temp.U_NAME}?start=getfile-{search_movie}")],
            [InlineKeyboardButton("🎥 Movie Request Group", url="https://t.me/RM_Movi")]
        ])

        movie_update_channel = await db.movies_update_channel_id()

        await bot.send_photo(
            chat_id=movie_update_channel or MOVIE_UPDATE_CHANNEL,
            photo=image_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons
        )

    except Exception as e:
        print("Movie update error:", e)
        await bot.send_message(LOG_CHANNEL, f"Movie update failed: {e}")


async def send_series_update(bot, series_title, season):
    try:
        episodes = series_files[series_title][season]
        sorted_eps = sorted(episodes.items())

        episode_lines = []
        for ep_num, ep_data in sorted_eps:
            link = f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{ep_data['file_id']}'>{ep_data['file_size']}</a>"
            episode_lines.append(EPISODE_CAPTION.format(ep_num, link))

        full_caption = UPDATE_CAPTION_SERIES.format(
            series_title, season, ep_data['language'], "\n".join(episode_lines)
        )

        poster = await fetch_movie_poster(series_title)
        image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get Full Season", url=f"https://t.me/{temp.U_NAME}?start=getfile-{series_title.replace(' ', '-')}-S{season:02d}")],
            [InlineKeyboardButton("🎥 Request Group", url="https://t.me/RM_Movi")]
        ])

        movie_update_channel = await db.movies_update_channel_id()

        await bot.send_photo(
            chat_id=movie_update_channel or MOVIE_UPDATE_CHANNEL,
            photo=image_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=buttons
        )

    except Exception as e:
        print("Series update error:", e)
        await bot.send_message(LOG_CHANNEL, f"Series update failed: {e}")


async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        query = title.strip().replace(" ", "+")
        url = f"https://jisshuapis.vercel.app/api.php?query={query}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
                return None
        except:
            return None


async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "WEB-DL"]
    return ", ".join(q for q in qualities if q.lower() in text.lower()) or "HDRip"


async def Jisshu_qualities(text, file_name):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    combined = (text + " " + file_name).lower()
    if "hevc" in combined:
        for q in qualities:
            if "HEVC" in q and q.split()[0].lower() in combined:
                return q
    for q in qualities:
        if "HEVC" not in q and q.lower() in combined:
            return q
    return "720p"


async def movie_name_format(name):
    return re.sub(
        r"http\S+", "",
        re.sub(r"[@#]\w+", "", name)
        .replace("_", " ").replace("[", "").replace("]", "")
        .replace("(", "").replace(")", "").replace("{", "").replace("}", "")
        .replace(".", " ").replace("@", "").replace(":", "").replace(";", "")
        .replace("'", "").replace("-", "").replace("!", "")
    ).strip()


def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"
