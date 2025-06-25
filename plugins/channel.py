# --| Created by: Jisshu_bots & SilentXBotz | Enhanced by ChatGPT |--#
import re
import hashlib
import asyncio
import aiohttp
from typing import Optional
from collections import defaultdict

from info import *
from utils import *
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam",
    "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish",
    "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu",
]

QUALITY_CAPTION = "\ud83d\udce6 {} : {}\n"

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
        formatted_name = await movie_name_format(original_name)
        file_title = formatted_name.strip()

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

async def send_movie_update(bot, file_name, files):
    try:
        if file_name in notified_movies:
            return
        notified_movies.add(file_name)

        imdb_data = await get_imdb(file_name)
        title = imdb_data.get("title", file_name).strip()
        if not title or len(title) <= 2:
            title = file_name

        kind = imdb_data.get("kind", "").strip().upper().replace(" ", "_") or "MOVIE"
        poster = await fetch_movie_poster(title, files[0].get("year"))
        image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        languages = set()
        for file in files:
            if file["language"] != "Not Idea":
                languages.update(file["language"].split(", "))
        language = ", ".join(sorted(languages)) or "Not Idea"

        quality_groups = defaultdict(list)
        for file in files:
            quality_groups[file["jisshuquality"]].append(file)

        sorted_qualities = sorted(quality_groups.keys())
        quality_links = []
        for quality in sorted_qualities:
            file_links = [
                f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{f['file_id']}'>{f['file_size']}</a>"
                for f in quality_groups[quality]
            ]
            quality_links.append(QUALITY_CAPTION.format(quality, " | ".join(file_links)))

        quality_text = "\n".join(quality_links)

        full_caption = f"""<b><blockquote>\ud83d\udcec NEW MOVIE ADDED \u2705</blockquote>

\ud83d\udea7 Title : {title}
\ud83c\udfa7 {language}
\ud83d\udd16 {kind}
<blockquote>\ud83d\ude80 Telegram Files \u2728</blockquote>

{quality_text}
<blockquote>\u303d\ufe0f Powered by @RM_Movie_Flix</blockquote></b>"""

        buttons = [
            [InlineKeyboardButton("\ud83d\udce5 Get All Files", url=f"https://t.me/{temp.U_NAME}?start=getfile-{title.replace(' ', '-')}")],
            [InlineKeyboardButton("\ud83c\udfa5 Movie Request Group", url="https://t.me/Movies_RM")]
        ]

        movie_update_channel = await db.movies_update_channel_id()
        await bot.send_photo(
            chat_id=movie_update_channel if movie_update_channel else MOVIE_UPDATE_CHANNEL,
            photo=image_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        print("Failed to send movie update. Error - ", e)
        await bot.send_message(LOG_CHANNEL, f"Failed to send movie update. Error - {e}")

async def send_series_update(bot, group_key, files):
    try:
        title = files[0]['title']
        season = files[0].get("season", "1")

        languages = set()
        for file in files:
            if file["language"] != "Not Idea":
                languages.update(file["language"].split(", "))
        language = ", ".join(sorted(languages)) or "Not Idea"

        links = []
        for f in sorted(files, key=lambda x: int(x["episode"] or 0)):
            ep = f"Ep {f['episode']}" if f['episode'] else "Unknown"
            links.append(f"\ud83d\udce6 {ep}: <a href='https://t.me/{temp.U_NAME}?start=file_0_{f['file_id']}'>{f['file_size']}</a>")

        quality_text = "\n".join(links)
        poster = await fetch_movie_poster(title, files[0].get("year")) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

        full_caption = f"""<b><blockquote>\ud83c\udfae NEW SERIES ADDED \u2705</blockquote>

\ud83c\udfac Title : {title}
\ud83d\udcc5 Season : {season}
\ud83c\udfa7 {language}
<blockquote>\ud83d\udcc1 Episodes:</blockquote>

{quality_text}
<blockquote>\u303d\ufe0f Powered by @RM_Movie_Flix</blockquote></b>"""

        buttons = [
            [InlineKeyboardButton("\ud83d\udce5 Get All Episodes", url=f"https://t.me/{temp.U_NAME}?start=getfile-{title.replace(' ', '-')}")],
            [InlineKeyboardButton("\ud83c\udfa5 Series Request Group", url="https://t.me/Movies_Rm")]
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

async def movie_name_format(file_name):
    filename = re.sub(r"http\S+", "", re.sub(r"@\w+|#\w+", "", file_name)
                      .replace("_", " ").replace("[", "").replace("]", "")
                      .replace("(", "").replace(")", "").replace("{", "")
                      .replace("}", "").replace(".", " ").replace("@", "")
                      .replace(":", "").replace(";", "").replace("'", "")
                      .replace("-", " ").replace("!", ""))
    filters = ["1080p", "720p", "480p", "2160p", "bluray", "hdrip", "webdl", "webrip", "dvdrip", "hevc", "x264", "x265", "10bit", "8bit", "aac", "mp3", "hindi", "english", "dual", "audio", "esub", "dubbed"]
    words = filename.lower().split()
    result = []
    for word in words:
        if word in filters:
            break
        result.append(word.capitalize())
    return " ".join(result).strip()

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]:
    async with aiohttp.ClientSession() as session:
        query = title.strip().replace(" ", "+")
        url = f"https://jisshuapis.vercel.app/api.php?query={query}"
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res:
                if res.status != 200:
                    print(f"API Error: HTTP {res.status}")
                    return None
                data = await res.json()
                for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                    posters = data.get(key)
                    if posters and isinstance(posters, list) and posters:
                        return posters[0]
                return None
        except Exception as e:
            print(f"Poster fetch error: {e}")
            return None

def format_file_size(size_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

async def get_qualities(text):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p", "HDRip", "WEB-DL"]
    return ", ".join([q for q in qualities if q.lower() in text.lower()])

async def Jisshu_qualities(text, file_name):
    qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"]
    combined_text = (text.lower() + " " + file_name.lower()).strip()
    if "hevc" in combined_text:
        for quality in qualities:
            if "hevc" in quality.lower() and quality.split()[0].lower() in combined_text:
                return quality
    for quality in qualities:
        if "hevc" not in quality.lower() and quality.lower() in combined_text:
            return quality
    return "720p"

async def get_imdb(file_name):
    try:
        formatted_name = await movie_name_format(file_name)
        imdb = await get_poster(formatted_name)
        if not imdb:
            return {}
        return {
            "title": imdb.get("title", formatted_name),
            "kind": imdb.get("kind", "Movie"),
            "year": imdb.get("year"),
            "url": imdb.get("url"),
        }
    except Exception as e:
        print(f"IMDB fetch error: {e}")
        return {}
