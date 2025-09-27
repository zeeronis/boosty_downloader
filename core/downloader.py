import asyncio
from pathlib import Path
from typing import Literal, Any, Optional, Awaitable

from boosty.api import download_file
from boosty.wrappers.media_pool import MediaPool
from core.completed_cache import CompletedCache
from core.defs import ContentType
from core.logger import logger
from core.meta import write_video_metadata
from core.utils import create_dir_if_not_exists
from core.stat_tracker import stat_tracker


class Downloader:
    def __init__(
            self,
            media_pool: MediaPool,
            base_path: Path,
            cache_path: Path,
            max_parallel_downloads: int = 10,
            save_meta: bool = False,
    ):
        self.media_pool = media_pool
        self.base_path = base_path
        self.cache_path = cache_path
        self.completed_cache = CompletedCache(cache_path)
        self._max_parallel_downloads = max_parallel_downloads
        self._save_meta = save_meta
        self._semaphore = asyncio.Semaphore(max_parallel_downloads)

    async def _download_file(
            self,
            file_url: str,
            path: Path
    ) -> tuple[bool, int]:
        logger.debug(f"call download_file func for \"{path.name}\"")
        success, total_size = await download_file(file_url, path)
        return success, total_size

    async def _get_file_and_raise_stat(
            self,
            url: str,
            path_file: Path,
            _t: Literal["p", "v", "a", "f"],
            file_id: str,
            post_id: str,
            expected_size: int = 0,
            metadata: dict[str, Any] | None = None
    ):
        if self.completed_cache.check(post_id, file_id):
            logger.info(f"File {file_id} from post {post_id} already downloaded (found in cache), skipping.")
            if _t == "p": stat_tracker.add_passed_photo()
            if _t == "v": stat_tracker.add_passed_video()
            if _t == "a": stat_tracker.add_passed_audio()
            if _t == "f": stat_tracker.add_passed_file()
            return

        match _t:
            case "p":
                passed, downloaded, error, meta_writer = stat_tracker.add_passed_photo, stat_tracker.add_downloaded_photo, stat_tracker.add_error_photo, None
            case "v":
                passed, downloaded, error, meta_writer = stat_tracker.add_passed_video, stat_tracker.add_downloaded_video, stat_tracker.add_error_video, write_video_metadata
            case "a":
                passed, downloaded, error, meta_writer = stat_tracker.add_passed_audio, stat_tracker.add_downloaded_audio, stat_tracker.add_error_audio, None
            case "f":
                passed, downloaded, error, meta_writer = stat_tracker.add_passed_file, stat_tracker.add_downloaded_file, stat_tracker.add_error_file, None
            case _:
                logger.warning(f"Unknown _t: {_t}")
                return

        async with self._semaphore:
            size_before = path_file.stat().st_size if path_file.is_file() else 0
            try:
                success, server_total_size = await self._download_file(url, path_file)
                if not success:
                    error()
                    return
                
                size_after = path_file.stat().st_size
                final_expected_size = expected_size if expected_size > 0 else server_total_size

                if final_expected_size > 0 and size_after >= final_expected_size:
                    if self._save_meta and meta_writer:
                        await meta_writer(path_file, metadata)
                    
                    if size_after > size_before:
                        downloaded()
                    else:
                        passed()
                    self.completed_cache.add(post_id, file_id)
                else:
                    logger.warning(f"File {path_file.name} is incomplete. "
                                 f"Expected {final_expected_size}, but got {size_after}. Will resume on next run.")
                    passed()

            except Exception as e:
                logger.warning(f"err download {url}", exc_info=e)
                error()

    async def download_by_content_type(self, content_type: ContentType):
        match content_type:
            case ContentType.IMAGE:
                await self.download_photos()
                return
            case ContentType.VIDEO:
                await self.download_videos()
                return
            case ContentType.AUDIO:
                await self.download_audios()
                return

    async def download_photos(self):
        tasks = []
        photo_path = self.base_path / "photos"
        create_dir_if_not_exists(photo_path)
        images = self.media_pool.get_images()
        for image in images:
            path = photo_path / (image["id"] + ".jpg")
            tasks.append(self._get_file_and_raise_stat(image["url"], path, "p", image["id"], image["post_id"]))
        await asyncio.gather(*tasks)

    async def download_videos(self):
        tasks = []
        video_path = self.base_path / "videos"
        create_dir_if_not_exists(video_path)
        videos = self.media_pool.get_videos()
        for video in videos:
            meta = video.get("meta")
            if meta and "title" in meta:
                post_name = meta.get("title")
            else:
                post_name = video["id"]
            path = video_path / (post_name + ".mp4")
            tasks.append(self._get_file_and_raise_stat(video["url"], path, "v", video["id"], video["post_id"], metadata=meta))
        await asyncio.gather(*tasks)

    async def download_audios(self):
        tasks = []
        audio_path = self.base_path / "audios"
        create_dir_if_not_exists(audio_path)
        audios = self.media_pool.get_audios()
        for audio in audios:
            path = audio_path / (audio["id"] + ".mp3")
            tasks.append(self._get_file_and_raise_stat(audio["url"], path, "a", audio["id"], audio["post_id"], audio["size_amount"]))
        await asyncio.gather(*tasks)

    async def download_files(self):
        tasks = []
        files_path = self.base_path / "files"
        create_dir_if_not_exists(files_path)
        files = self.media_pool.get_files()
        for file in files:
            path = files_path / file["title"]
            tasks.append(self._get_file_and_raise_stat(file["url"], path, "f", file["id"], file["post_id"], file["size_amount"]))
        await asyncio.gather(*tasks)