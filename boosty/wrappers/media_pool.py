from typing import Any, List, Dict
from core.defs import AsciiCommands

from core.logger import logger
from core.config import conf


class MediaPool:

    __images: dict
    __videos: dict
    __audios: dict
    __files: dict

    def __init__(self):
        self.__videos = {}
        self.__images = {}
        self.__audios = {}
        self.__files = {}

    def add_image(self, _id: str, post_id: str, url: str, width: int, height: int):
        if not conf.need_load_photo:
            return
        total_weight = width * height
        current = self.__images.get(_id)
        if current:
            if total_weight < current["total_weight"]:
                return
        self.__images[_id] = {
            "total_weight": total_weight,
            "url": url,
            "post_id": post_id,
        }

    def add_video(self, _id: str, post_id: str, url: str, size_amount: int, meta: dict[str, Any]):
        if not conf.need_load_video:
            return
        if size_amount > conf.max_video_file_size:
            return
        current = self.__videos.get(_id)
        if current:
            if size_amount < current["size_amount"]:
                return
        self.__videos[_id] = {
            "url": url,
            "size_amount": size_amount,
            "meta": meta,
            "post_id": post_id,
        }

    def add_audio(self, _id: str, post_id: str, url: str, size_amount: int):
        if not conf.need_load_audio:
            return
        current = self.__audios.get(_id)
        if current:
            if size_amount < current["size_amount"]:
                return
        self.__audios[_id] = {
            "url": url,
            "size_amount": size_amount,
            "post_id": post_id,
        }

    def add_file(self, _id: str, post_id: str, url: str, size_amount: int, title: str):
        if not conf.need_load_files:
            return
        current = self.__files.get(_id)
        if current:
            return
        self.__files[_id] = {
            "url": url,
            "size_amount": size_amount,
            "title": title,
            "post_id": post_id,
        }

    def get_images(self) -> List[Dict]:
        """
        Get all images
        :return: [{"id": "1", "post_id": "post1", "url": "https://s3.com/1"}, ...]
        """
        res = []
        for img_id, img_data in self.__images.items():
            res.append(
                {
                    "id": img_id,
                    "url": img_data["url"],
                    "post_id": img_data["post_id"],
                }
            )
        return res

    def get_videos(self) -> List[Dict]:
        """
        Get all videos
        :return: [{"id": "1", "post_id": "post1", "url": "https://s3.com/1", "meta": {}, "size_amount": 123}, ...]
        """
        res = []
        for video_id, video_data in self.__videos.items():
            res.append(
                {
                    "id": video_id,
                    "url": video_data["url"],
                    "meta": video_data["meta"],
                    "post_id": video_data["post_id"],
                    "size_amount": video_data["size_amount"],
                }
            )
        return res

    def get_audios(self) -> List[Dict]:
        """
        Get all audios
        :return: [{"id": "1", "post_id": "post1", "url": "https://s3.com/1", "size_amount": 123}, ...]
        """
        res = []
        for audio_id, audio_data in self.__audios.items():
            res.append(
                {
                    "id": audio_id,
                    "url": audio_data["url"],
                    "post_id": audio_data["post_id"],
                    "size_amount": audio_data["size_amount"],
                }
            )
        return res

    def get_files(self) -> List[Dict]:
        """
        Get all files
        :return: [{"id": "1", "post_id": "post1", "url": "https://s3.com/1", "title": "1.pdf", "size_amount": 123}, ...]
        """
        res = []
        for file_id, file_data in self.__files.items():
            res.append(
                {
                    "id": file_id,
                    "url": file_data["url"],
                    "title": file_data["title"],
                    "post_id": file_data["post_id"],
                    "size_amount": file_data["size_amount"],
                }
            )
        return res

    def get_first(self) -> Dict | None:
        images = self.get_images()
        if images and len(images) > 0:
            return images[0]
        videos = self.get_videos()
        if videos and len(videos) > 0:
            return videos[0]
        audios = self.get_audios()
        if audios and len(audios) > 0:
            return audios[0]
        files = self.get_files()
        if files and len(files) > 0:
            return files[0]
        return None

    def print_files_count(self):
        logger.info(f"scanning... "
               f"images {AsciiCommands.COLORIZE_HIGHLIGHT.value}{len(self.__images)}{AsciiCommands.COLORIZE_DEFAULT.value}, "
               f"videos {AsciiCommands.COLORIZE_HIGHLIGHT.value}{len(self.__videos)}{AsciiCommands.COLORIZE_DEFAULT.value}, "
               f"audios {AsciiCommands.COLORIZE_HIGHLIGHT.value}{len(self.__audios)}{AsciiCommands.COLORIZE_DEFAULT.value}, "
               f"files {AsciiCommands.COLORIZE_HIGHLIGHT.value}{len(self.__files)}{AsciiCommands.COLORIZE_DEFAULT.value}")