#--| Modified by ChatGPT for Series + Movie Support |--# import re import hashlib import asyncio from info import * from utils import * from pyrogram import Client, filters, enums from database.users_chats_db import db from database.ia_filterdb import save_file, unpack_new_file_id from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton import aiohttp from typing import Optional from collections import defaultdict
import re
import hashlib
import asyncio
from info import *
from utils import *
from pyrogram import Client, filters, enums
from database.users_chats_db import db
from database.ia_filterdb import save_file, unpack_new_file_id
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
from typing import Optional
from collections import defaultdict

CAPTION_LANGUAGES = ["Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla", "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli", "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German", "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia", "Assamese", "Urdu"]

UPDATE_CAPTION = """<b><blockquote>📨 𝖭𝖤𝖶 𝖥𝖨𝖫𝖤 𝖠𝖣𝖣𝖤𝖣 ✅</blockquote>

🚧  Title : {} 🎧 Audio : {} 🔖 Type : {}

<blockquote>🚀 Telegram Files ✨</blockquote>{}

<blockquote>〽️ Powered by @RM_Movie_Flix</b></blockquote>
"""notified_movies = set() movie_files = defaultdict(list) POST_DELAY = 10 processing_movies = set() media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter) async def media(bot, message): bot_id = bot.me.id media = getattr(message, message.media.value, None) if media.mime_type in ['video/mp4', 'video/x-matroska', 'document/mp4']: media.file_type = message.media.value media.caption = message.caption success_sts = await save_file(media) if success_sts == 'suc' and await db.get_send_movie_update_status(bot_id): await queue_movie_file(bot, media)

async def queue_movie_file(bot, media): try: file_name = await movie_name_format(media.file_name) caption = await movie_name_format(media.caption) year_match = re.search(r"\b(19|20)\d{2}\b", caption) year = year_match.group(0) if year_match else None season_match = re.search(r"(?i)(?:s|season)0*(\d{1,2})", caption) or re.search(r"(?i)(?:s|season)0*(\d{1,2})", file_name) episode_match = re.search(r"(?i)(?:e|ep|episode)[\s_:-]0(\d{1,2})", caption) or 
re.search(r"(?i)(?:e|ep|episode)[\s_:-]0(\d{1,2})", file_name) episode_number = int(episode_match.group(1)) if episode_match else None

if year:
        file_name = file_name[:file_name.find(year) + 4]
    elif season_match:
        season = season_match.group(1)
        file_name = file_name[:file_name.find(season) + 1]

    quality = await get_qualities(caption) or "HDRip"
    jisshuquality = await Jisshu_qualities(caption, media.file_name) or "720p"
    language = ", ".join([lang for lang in CAPTION_LANGUAGES if lang.lower() in caption.lower()]) or "Not Idea"
    file_size_str = format_file_size(media.file_size)
    file_id, _ = unpack_new_file_id(media.file_id)

    movie_files[file_name].append({
        "quality": quality,
        "jisshuquality": jisshuquality,
        "file_id": file_id,
        "file_size": file_size_str,
        "caption": caption,
        "language": language,
        "year": year,
        "episode": episode_number
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

async def send_movie_update(bot, file_name, files): try: if file_name in notified_movies: return notified_movies.add(file_name)

imdb_data = await get_imdb(file_name)
    title = imdb_data.get("title", file_name)
    kind = imdb_data.get("kind", "Movie").strip().upper().replace(" ", "_")
    kind = f"#{kind}" if kind else "#MOVIE"
    poster = await fetch_movie_poster(title, files[0]["year"])

    languages = set()
    for file in files:
        if file["language"] != "Not Idea":
            languages.update(file["language"].split(", "))
    language = " ".join([f"#{lang.replace(' ', '')}" for lang in sorted(languages)]) or "#Unknown"

    is_series = any(file.get("episode") for file in files)

    if is_series:
        files = sorted(files, key=lambda x: x.get("episode", 0))
        lines = []
        for f in files:
            ep = f.get("episode", "?")
            q = f"#{f['jisshuquality'].replace(' ', '')}"
            link = f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{f['file_id']}'>{f['file_size']}</a>"
            lines.append(f"🎥 Episode {ep} ({q}) : {link}")
        quality_text = "\n".join(lines)
    else:
        grouped = defaultdict(list)
        for f in files:
            grouped[f["jisshuquality"]].append(f)
        quality_text = ""
        for q in sorted(grouped):
            tag_q = f"#{q.replace(' ', '')}"
            links = [f"<a href='https://t.me/{temp.U_NAME}?start=file_0_{f['file_id']}'>{f['file_size']}</a>" for f in grouped[q]]
            quality_text += f"\n{tag_q} : {' | '.join(links)}"

    image_url = poster or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"

    search_movie = file_name.replace(" ", "-")
    btn = [[
        InlineKeyboardButton("\ud83d\udcc5 Get All Files", url=f"https://t.me/{temp.U_NAME}?start=getfile-{search_movie}")
    ], [
        InlineKeyboardButton("\ud83c\udfa5 Movie Request Group", url="https://t.me/Movies_Rm")
    ]]

    full_caption = UPDATE_CAPTION.format(title, language, kind, quality_text)
    movie_update_channel = await db.movies_update_channel_id()

    await bot.send_photo(
        chat_id=movie_update_channel or MOVIE_UPDATE_CHANNEL,
        photo=image_url,
        caption=full_caption,
        reply_markup=InlineKeyboardMarkup(btn),
        parse_mode=enums.ParseMode.HTML
    )
except Exception as e:
    print(f"Failed to send movie update: {e}")

async def get_imdb(file_name): try: formatted = await movie_name_format(file_name) imdb = await get_poster(formatted) return imdb or {} except Exception as e: print(f"IMDB fetch error: {e}") return {}

async def fetch_movie_poster(title: str, year: Optional[int] = None) -> Optional[str]: async with aiohttp.ClientSession() as session: query = title.strip().replace(" ", "+") url = f"https://jisshuapis.vercel.app/api.php?query={query}" try: async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as res: if res.status != 200: return None data = await res.json() for key in ["jisshu-2", "jisshu-3", "jisshu-4"]: posters = data.get(key) if posters and isinstance(posters, list): return posters[0] except: return None

async def get_qualities(text): tags = ["480p", "720p", "720p HEVC", "1080p", "ORG", "HDCAM", "HDRip", "WEB-DL", "HDTS"] return ", ".join([q for q in tags if q.lower() in text.lower()])

async def Jisshu_qualities(text, fname): qualities = ["480p", "720p", "720p HEVC", "1080p", "1080p HEVC", "2160p"] combined = (text + " " + fname).lower() if "hevc" in combined: for q in qualities: if "hevc" in q.lower() and q.split()[0] in combined: return q for q in qualities: if q.lower() in combined: return q return "720p"

async def movie_name_format(name): name = re.sub(r'http\S+', '', name) name = re.sub(r'[@#]\w+', '', name) return re.sub(r'[_().:{};"'"!@-]', ' ', name).strip()

def format_file_size(size): for unit in ['B', 'KB', 'MB', 'GB', 'TB']: if size < 1024: return f"{size:.2f} {unit}" size /= 1024 return f"{size:.2f} PB"

