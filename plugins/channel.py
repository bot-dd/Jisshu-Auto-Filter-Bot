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
from typing import Optional, List, Dict, Set
from collections import defaultdict

CAPTION_LANGUAGES = [
    "Bhojpuri", "Hindi", "Bengali", "Tamil", "English", "Bangla",
    "Telugu", "Malayalam", "Kannada", "Marathi", "Punjabi", "Bengoli",
    "Gujrati", "Korean", "Gujarati", "Spanish", "French", "German",
    "Chinese", "Arabic", "Portuguese", "Russian", "Japanese", "Odia",
    "Assamese", "Urdu"
]

UPDATE_CAPTION = """
🎬 <b>𝖭𝖤𝖶 𝖬𝖮𝖵𝖨𝖤 𝖠𝖣𝖣𝖤𝖣</b> ✅

📌 <b>Title:</b> {}
🎧 <b>Audio:</b> {} | 🗂 <b>Type:</b> {}
📆 <b>Year:</b> {}

🚀 <b>Available Qualities:</b>
{}

〽️ <b>Powered by</b> @RM_Movie_Flix
"""

QUALITY_CAPTION = "┣📦 <b>#{}:</b> {}\n"

# Global state management
processing_movies: Set[str] = set()
movie_files: Dict[str, List[dict]] = defaultdict(list)
POST_DELAY = 10  # seconds
movie_lock = asyncio.Lock()

# Supported media types
media_filter = filters.document | filters.video | filters.audio

def safe_extract(pattern: str, text: str, group: int = 1) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(group) if match else None

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media_handler(bot: Client, message):
    try:
        bot_id = bot.me.id
        media = getattr(message, message.media.value, None)
        
        if not media or not hasattr(media, 'mime_type'):
            return
            
        valid_mime_types = [
            'video/mp4', 'video/x-matroska', 'video/quicktime',
            'document/mp4', 'application/x-matroska'
        ]
        
        if media.mime_type in valid_mime_types:
            media.file_type = message.media.value
            media.caption = message.caption or ""
            success_sts = await save_file(media)
            
            if success_sts == 'suc' and await db.get_send_movie_update_status(bot_id):
                await queue_movie_file(bot, media)
                
    except Exception as e:
        error_msg = f"Media Handler Error: {str(e)}"
        await bot.send_message(LOG_CHANNEL, error_msg)
        print(error_msg)

async def queue_movie_file(bot: Client, media):
    try:
        file_name = media.file_name or ""
        caption = media.caption or ""
        clean_name = await movie_name_format(file_name, caption)
        
        # Extract year from filename or caption
        year = safe_extract(r'\b(19|20)\d{2}\b', caption) or safe_extract(r'\b(19|20)\d{2}\b', file_name)
        
        # Extract season information
        season = safe_extract(r'(?:s|season)\s*(\d{1,2})', caption) or safe_extract(r'(?:s|season)\s*(\d{1,2})', file_name)
        
        # Quality detection
        quality = await detect_quality(caption, file_name)
        file_size = format_file_size(media.file_size)
        file_id, _ = unpack_new_file_id(media.file_id)
        
        # Language detection
        languages = detect_languages(caption)
        language = ", ".join(languages) if languages else "Multi"
        
        # Create unique movie ID
        movie_id = f"{clean_name}_{year}" if year else clean_name
        
        async with movie_lock:
            # Check if already processing
            if movie_id in processing_movies:
                movie_files[movie_id].append({
                    "quality": quality,
                    "file_id": file_id,
                    "file_size": file_size
                })
                return
                
            # Add to processing
            processing_movies.add(movie_id)
            movie_files[movie_id] = [{
                "quality": quality,
                "file_id": file_id,
                "file_size": file_size,
                "year": year,
                "language": language,
                "season": season
            }]
        
        # Wait for additional files
        await asyncio.sleep(POST_DELAY)
        
        # Process collected files
        async with movie_lock:
            files_to_send = movie_files.pop(movie_id, [])
            if movie_id in processing_movies:
                processing_movies.remove(movie_id)
        
        if files_to_send:
            await send_movie_update(bot, clean_name, files_to_send)
            
    except Exception as e:
        error_msg = f"Queue Error: {str(e)}"
        await bot.send_message(LOG_CHANNEL, error_msg)
        print(error_msg)
        async with movie_lock:
            processing_movies.discard(clean_name)

async def send_movie_update(bot: Client, movie_name: str, files: List[dict]):
    try:
        # Get common metadata
        year = files[0].get("year", "N/A")
        language = files[0].get("language", "Multi")
        season = files[0].get("season")
        
        # Get IMDb data
        imdb_data = await get_imdb(movie_name, year)
        title = imdb_data.get("title", movie_name)
        kind = imdb_data.get("kind", "Movie")
        
        # Add season info to title if available
        if season:
            title = f"{title} - Season {season}"
        
        # Get poster
        poster_url = await fetch_movie_poster(title, year) or "https://te.legra.ph/file/88d845b4f8a024a71465d.jpg"
        
        # Group files by quality
        quality_groups = defaultdict(list)
        for file in files:
            quality_groups[file["quality"]].append(file)
        
        # Generate quality list
        quality_text = ""
        for quality, items in sorted(quality_groups.items()):
            file_links = []
            for idx, item in enumerate(items, 1):
                file_links.append(
                    f"<a href='https://t.me/{temp.U_NAME}?start=file_{item['file_id']}'>"
                    f"📁 {quality} {idx} ({item['file_size']})</a>"
                )
            quality_text += QUALITY_CAPTION.format(
                quality, 
                " | ".join(file_links)
            )
        
        # Format final caption
        full_caption = UPDATE_CAPTION.format(
            title, 
            language, 
            kind, 
            year or "N/A",
            quality_text.strip()
        )
        
        # Create buttons
        btn = [
            [InlineKeyboardButton("📥 Download All Files", 
             url=f"https://t.me/{temp.U_NAME}?start=allfiles_{hashlib.md5(title.encode()).hexdigest()}")],
            [InlineKeyboardButton("🎬 Request Movies", url="https://t.me/Movies_Rm")]
        ]
        
        # Get update channel
        channel_id = await db.movies_update_channel_id() or MOVIE_UPDATE_CHANNEL
        
        # Send update
        await bot.send_photo(
            chat_id=channel_id,
            photo=poster_url,
            caption=full_caption,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(btn)
        )
        
    except Exception as e:
        error_msg = f"Send Update Error: {str(e)}"
        await bot.send_message(LOG_CHANNEL, error_msg)
        print(error_msg)

async def get_imdb(title: str, year: Optional[str]) -> dict:
    try:
        return await get_poster(title, year=year) or {}
    except Exception:
        return {"title": title, "kind": "Movie"}

async def fetch_movie_poster(title: str, year: Optional[str]) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            query = f"{title} {year}" if year else title
            url = f"https://jisshuapis.vercel.app/api.php?query={query.replace(' ', '+')}"
            
            async with session.get(url, timeout=10) as res:
                if res.status == 200:
                    data = await res.json()
                    for key in ["jisshu-2", "jisshu-3", "jisshu-4"]:
                        if data.get(key):
                            return data[key][0]
    except Exception:
        return None

def detect_languages(text: str) -> List[str]:
    text_lower = text.lower()
    return [lang for lang in CAPTION_LANGUAGES if lang.lower() in text_lower]

async def detect_quality(*texts: str) -> str:
    QUALITY_PRIORITY = [
        "2160p", "1080p HEVC", "1080p", "720p HEVC", "720p", 
        "480p", "HDCAM", "HDRip", "WEB-DL", "DVDRip", "HDTC", "HDTS"
    ]
    
    combined_text = " ".join(t for t in texts if t).lower()
    
    for quality in QUALITY_PRIORITY:
        if quality.lower() in combined_text:
            return quality
    
    return "720p"  # Default quality

async def movie_name_format(*texts: str) -> str:
    """Extract clean movie name from filename/caption"""
    text = " ".join(t for t in texts if t)
    # Remove unwanted characters and metadata
    clean_text = re.sub(
        r'http\S+|@\w+|#\w+|[_\-\+\[\]\(\)\{\}\.\!\:\;]|WEB-DL|HDRip|BluRay|x264|AAC|\d{3,4}p',
        ' ', 
        text,
        flags=re.IGNORECASE
    )
    # Remove extra spaces and trim
    return " ".join(clean_text.split()).strip().title()

def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable format"""
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    while size_bytes >= 1024 and unit_idx < len(units)-1:
        size_bytes /= 1024.0
        unit_idx += 1
    return f"{size_bytes:.2f} {units[unit_idx]}"
