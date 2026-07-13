import os
from typing import Literal
import asyncio
import aiohttp
import webbrowser
import urllib.parse
import re
from livekit.agents import function_tool
import logging
logger = logging.getLogger(__name__)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

@function_tool()
async def play_media(media_name: str, media_type: Literal["song", "video"] = "song") -> str:
    """
    Plays media content from YouTube.
    
    Args:
        media_name: Name of song/video
        media_type: Content type (default: "song")
        
    Behavior:
        - Uses YouTube Data API if key available
        - Falls back to browser scraping to play the first result
        
    Returns:
        str: Currently playing confirmation or search link

    """
    try:
        print(f"🎵 Playing media: {media_name} (type: {media_type})")
        encoded_name = urllib.parse.quote(media_name)
        
        if not YOUTUBE_API_KEY:
            # Fallback: Scrape the first video ID
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://www.youtube.com/results?search_query={encoded_name}", timeout=10) as response:
                    html = await response.text()
            
            video_ids = re.findall(r'watch\?v=(\S{11})', html)
            if video_ids:
                video_id = video_ids[0]
                await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/watch?v={video_id}&autoplay=1"))
                return f"🎵 YouTube पर '{media_name}' प्ले कर रहा हूँ..."
            else:
                await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/results?search_query={encoded_name}"))
                return f"YouTube पर '{media_name}' खोल रहा हूँ..."
            
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={encoded_name}&type=video&key={YOUTUBE_API_KEY}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                data = await response.json()
        
        if data.get('items'):
            video = data['items'][0]
            await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/watch?v={video['id']['videoId']}&autoplay=1"))
            return f"🎵 अब बज रहा है: {video['snippet']['title']}"
        
        await asyncio.create_task(asyncio.to_thread(webbrowser.open, f"https://www.youtube.com/results?search_query={encoded_name}"))
        return f"YouTube पर '{media_name}' खोल रहा हूँ..."
    except Exception as e:
        logger.error(f"मीडिया त्रुटि: {e}")
        return f"❌ मीडिया चलाने में समस्या आई: {str(e)}"

