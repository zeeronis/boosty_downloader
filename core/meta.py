from pathlib import Path
from typing import Any, Optional
from core.logger import logger
from mutagen.mp4 import MP4, MP4Cover
import aiohttp


def parse_metadata(post: dict[str, Any], media: dict[str, Any]) -> dict[str, Any]:
    metadata = {}
    if "title" in post:
        metadata["title"] = post["title"]
    if "preview" in media:
        metadata["cover"] = media["preview"]
    return metadata


async def write_video_metadata(file_path: Path, metadata: dict[str, Any] | None):
    """
    Write metadata to MP4 file

    Parameters:
    file_path (str): Path to the MP4 file
    metadata (dict): Dictionary containing metadata fields
    """

    if not metadata:
        return

    cover_data: Optional[bytes] = None
    if "cover" in metadata:
        try:
            async with aiohttp.ClientSession() as conn:
                resp = await conn.get(metadata["cover"])
                resp.raise_for_status()
                cover_data = await resp.read()
        except aiohttp.ClientError as e:
            logger.warning(f"Could not download cover image for {file_path.name}. Reason: {e}")

    try:
        video = MP4(file_path)

        if "title" in metadata:
            video["\xa9nam"] = metadata["title"]

        if "description" in metadata:
            video["desc"] = metadata["description"]
        
        if cover_data:
            video['covr'] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

        video.save()

    except Exception as e:
        logger.exception(f"Error writing metadata to {file_path.name}", exc_info=e)