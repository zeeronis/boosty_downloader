import asyncio
import os
import time
from pathlib import Path
from typing import Optional, Any

import aiofiles
from aiohttp import ClientSession
from copy import copy
from tqdm.asyncio import tqdm

from boosty.defs import MediaType
from boosty.wrappers.post import Post
from boosty.wrappers.post_pool import PostPool
from core.config import conf
from boosty.wrappers.media_pool import MediaPool
from boosty.defs import DEFAULT_LIMIT, DEFAULT_LIMIT_BY, BOOSTY_API_BASE_URL, DEFAULT_HEADERS, DOWNLOAD_HEADERS
from core.defs import VIDEO_QUALITY, ContentType
from core.logger import logger
from core.stat_tracker import stat_tracker
from core.utils import get_terminal_width


async def get_media_list(
    session: ClientSession,
    content_type: ContentType,
    creator_name: str,
    use_cookie: bool,
    limit: int = DEFAULT_LIMIT,
    limit_by: str = DEFAULT_LIMIT_BY,
    offset: str = None
):
    if isinstance(content_type, ContentType):
        media_type = content_type.value
    else:
        media_type = content_type
    params = {
        "type": media_type,
        "limit": limit,
        "limit_by": limit_by
    }
    if offset:
        params["offset"] = offset
    try:
        send_headers = copy(DEFAULT_HEADERS)
        if use_cookie and conf.ready_to_auth():
            send_headers["Cookie"] = conf.cookie
            send_headers["Authorization"] = conf.authorization
        url = BOOSTY_API_BASE_URL + f"/v1/blog/{creator_name}/media_album/"
        logger.debug("GET " + url + f" offset={offset} media_type={media_type}")
        resp = await session.get(
            url,
            params=params,
            headers=send_headers
        )
        result = await resp.json()
    except Exception as e:
        logger.error("Failed get media album", exc_info=e)
        result = None
    return result


async def get_all_media_by_type(
    content_type: ContentType,
    creator_name: str,
    media_pool: MediaPool,
    use_cookie: bool,
    offset: Optional[str] = None
) -> tuple[Any, Any]:
    load_posts_chunk_count = 10
    logger.info(f"get next {load_posts_chunk_count} media posts by type \"{content_type.value}\" for \"{creator_name}\". Offset: {offset}")
    async with ClientSession() as session:
        for i in range(load_posts_chunk_count):
            resp = await get_media_list(
                session=session,
                creator_name=creator_name,
                content_type=content_type,
                use_cookie=use_cookie,
                offset=offset
            )
            if not resp:
                logger.warning(f"get next {load_posts_chunk_count} media posts by type \"{content_type.value}\" for \"{creator_name}\". Offset: {offset}. Failed due unknown reason, rerun...")
                await asyncio.sleep(0.3)
                continue
            extra = resp["extra"]
            media_posts = resp["data"]["mediaPosts"]
            for post in media_posts:
                if post["post"]["hasAccess"]:
                    post_id = post["post"]["id"]
                    for media in post["media"]:
                        if content_type == ContentType.IMAGE:
                            media_pool.add_image(
                                _id=media["id"],
                                post_id=post_id,
                                url=media["url"],
                                width=media["width"],
                                height=media["height"],
                            )
                        elif content_type == ContentType.AUDIO:
                            media_pool.add_audio(
                                _id=media["id"],
                                post_id=post_id,
                                url=media["url"] + post["post"].get("signedQuery", ""),
                                size_amount=media["size"]
                            )
                        elif content_type == ContentType.VIDEO:
                            for url in media["playerUrls"]:
                                if url["type"] in VIDEO_QUALITY.keys() and url["url"] != "":
                                    media_pool.add_video(
                                        _id=media["id"],
                                        post_id=post_id,
                                        url=url["url"],
                                        size_amount=VIDEO_QUALITY[url["type"]],
                                        meta={"title": post["post"].get("title")},
                                    )
            return extra["isLast"], extra["offset"]
    return True, None


async def download_file(url: str, path: Path) -> tuple[bool, int]:
    if url == "":
        logger.warning(f"Empty URL for {path} file, skip")
        return False, 0
    try:
        file_name = path.name
        async with ClientSession() as session:
            initial_bytes = 0
            if path.is_file():
                initial_bytes = path.stat().st_size

            headers = copy(DEFAULT_HEADERS)
            headers.update(DOWNLOAD_HEADERS)
            if initial_bytes > 0:
                headers["Range"] = f"bytes={initial_bytes}-"

            for i in range(3):
                logger.debug(f"url: {url}")
                try:
                    response = await session.get(
                        url,
                        headers=headers,
                        allow_redirects=True,
                        timeout=conf.download_timeout
                    )

                    file_mode = "wb"
                    total_length = 0

                    content_length_str = response.headers.get("Content-Length")
                    try:
                        content_length = int(content_length_str) if content_length_str else 0
                        if content_length < 0:
                            content_length = 0
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse Content-Length header: {content_length_str}")
                        content_length = 0

                    if response.status == 206:  # Partial Content
                        file_mode = "ab"
                        content_range = response.headers.get("Content-Range")
                        if content_range:
                            try:
                                total_length = int(content_range.split("/")[-1])
                            except (ValueError, IndexError):
                                logger.warning(f"Could not parse Content-Range header: {content_range}")
                                total_length = initial_bytes + content_length
                        else:
                            total_length = initial_bytes + content_length
                    elif response.status == 200:  # OK
                        if initial_bytes > 0:
                            logger.warning(f"Server does not support resume for \"{file_name}\". Restarting download.")
                            initial_bytes = 0
                        file_mode = "wb"
                        total_length = content_length
                    elif response.status == 416:  # Range Not Satisfiable
                        return True, initial_bytes
                    else:
                        logger.warning(f"non-2xx status code ({response.status}) for file {url}, try {i + 2}")
                        await asyncio.sleep(0.5)
                        continue

                    async with aiofiles.open(path, file_mode) as file:
                        pb_size = get_terminal_width()
                        max_file_name_length = 40
                        if len(file_name) > max_file_name_length:
                            file_name_formatted = f"\033[92m...{file_name[-(max_file_name_length-4):]}\033[0m"
                            file_name_formatted += ' ' * 1
                        else:
                            file_name_formatted = f"\033[92m{file_name}\033[0m"
                            file_name_formatted += ' ' * (max_file_name_length - len(file_name))
                        with tqdm(
                                bar_format = "{percentage:3.0f}% |{bar}{r_bar} {desc}",
                                desc = file_name_formatted,
                                ncols = pb_size,
                                initial = initial_bytes,
                                total = total_length,
                                unit = 'B',
                                unit_scale = True,
                                unit_divisor = 1024,
                        ) as pbar:
                            chunk_size = conf.download_chunk_size
                            async for content in response.content.iter_chunked(chunk_size):
                                await file.write(content)
                                pbar.update(len(content))
                    return True, total_length
                except Exception as e:
                    if "Invalid character in Content-Length" in str(e):
                        logger.warning(
                            f"Corrupted download for {path.name} due to invalid Content-Length. "
                            f"Truncating file and retrying."
                        )
                        try:
                            current_size = path.stat().st_size
                            truncate_size = 5 * 1024 * 1024  # 5 MB
                            new_size = max(0, current_size - truncate_size)
                            
                            with open(path, 'r+b') as f:
                                f.truncate(new_size)

                            initial_bytes = new_size
                            if initial_bytes > 0:
                                headers["Range"] = f"bytes={initial_bytes}-"
                            else:
                                headers.pop("Range", None)

                        except OSError as truncate_error:
                            logger.error(f"Could not truncate corrupted file {path.name}: {truncate_error}")
                            return False, 0
                        
                        await asyncio.sleep(0.5)
                        continue

                    logger.warning(f"failed to download or write file {path}: {e}, trying again")
                    await asyncio.sleep(0.5)
                    continue

            # after loop
            logger.error(f"actually failed download file {url}")
            return False, 0

    except TimeoutError:
        lg = "[TimedOut] Failed download media due to timeout. " \
             "If file is large, try to set a higher value for the download_timeout parameter in config"
        logger.error(lg)
        stat_tracker.add_download_error(url)
        return False, 0
    except Exception as e:
        logger.error(f"[{e.__class__.__name__}] Failed download media: {e}")
        stat_tracker.add_download_error(url)
        return False, 0


async def get_profile_stat(creator_name: str):
    url = BOOSTY_API_BASE_URL + f"/v1/blog/{creator_name}/media_album/counters/"
    async with ClientSession() as session:
        headers = copy(DEFAULT_HEADERS)
        response = await session.get(
            url,
            headers=headers
        )
        if response.status == 200:
            data = await response.json()
            stat_tracker.total_photos = data["data"]["mediaCounters"]["image"]
            stat_tracker.total_videos = data["data"]["mediaCounters"]["okVideo"]
            stat_tracker.total_audios = data["data"]["mediaCounters"]["audioFile"]
        else:
            logger.warning("FAILED GET PROFILE STAT")


async def get_post_list(
    session: ClientSession,
    creator_name: str,
    use_cookie: bool,
    limit: int = DEFAULT_LIMIT,
    limit_by: str = DEFAULT_LIMIT_BY,
    offset: str = None,
):
    params = {
        "limit": limit,
        "limit_by": limit_by,
        "reply_limit": 1,
        "comments_limit": 0,
    }
    if offset:
        params["offset"] = offset
    try:
        send_headers = copy(DEFAULT_HEADERS)
        if use_cookie and conf.ready_to_auth():
            send_headers["Cookie"] = conf.cookie
            send_headers["Authorization"] = conf.authorization
        url = BOOSTY_API_BASE_URL + f"/v1/blog/{creator_name}/post/"
        logger.info("GET " + url + f" offset={offset}")
        resp = await session.get(
            url,
            params=params,
            headers=send_headers
        )
        if resp.status != 200:
            raise Exception(f"{resp.status} on get posts")
        result = await resp.json()
    except Exception as e:
        logger.error("Failed get posts", exc_info=e)
        result = None
    return result


async def get_all_posts(
    creator_name: str,
    post_pool: PostPool,
    use_cookie: bool,
    offset: Optional[str] = None,
):
    logger.info(f"get posts for {creator_name}")
    async with ClientSession() as session:
        for i in range(10):
            resp = await get_post_list(
                session=session,
                creator_name=creator_name,
                use_cookie=use_cookie,
                offset=offset
            )
            if not resp:
                continue
            extra = resp["extra"]
            posts = resp["data"]
            for post in posts:
                if post["hasAccess"]:
                    new_post = Post(
                        _id=post["id"],
                        title=post["title"],
                        markdown_text=conf.post_text_in_markdown,
                        publish_time=post["publishTime"]
                    )
                    signed_query = post.get("signedQuery", "")
                    for media in post["data"]:
                        if media["type"] == MediaType.VIDEO.value:
                            for url in media["playerUrls"]:
                                if url["type"] in VIDEO_QUALITY.keys() and url["url"] != "":
                                    new_post.media_pool.add_video(
                                        _id=media["id"],
                                        post_id=post["id"],
                                        url=url["url"],
                                        size_amount=VIDEO_QUALITY[url["type"]],
                                        meta={"title": post.get("title")},
                                    )
                        elif media["type"] == MediaType.IMAGE.value:
                            new_post.media_pool.add_image(
                                _id=media["id"],
                                post_id=post["id"],
                                url=media["url"],
                                width=media["width"],
                                height=media["height"]
                            )
                        elif media["type"] == MediaType.AUDIO.value:
                            new_post.media_pool.add_audio(
                                _id=media["id"],
                                post_id=post["id"],
                                url=media["url"] + signed_query,
                                size_amount=media["size"],
                            )
                        elif media["type"] == MediaType.FILE.value:
                            new_post.media_pool.add_file(
                                _id=media["id"],
                                post_id=post["id"],
                                url=media["url"] + signed_query,
                                size_amount=media["size"],
                                title=media["title"]
                            )
                        elif media["type"] == MediaType.TEXT.value:
                            if media["modificator"] == "":
                                new_post.add_marshaled_text(media["content"])
                            elif media["modificator"] == "BLOCK_END":
                                new_post.add_block_end()
                        elif media["type"] == MediaType.LINK.value:
                            new_post.add_link(media["content"], media["url"])
                    post_pool.add_post(new_post, offset)
            if extra["isLast"]:
                post_pool.close()
            post_pool.set_offset(extra["offset"])
            return
        logger.error("Break posts get due errors")


async def fetch_post_by_id(
    session: ClientSession,
    creator_name: str,
    post_id: str,
    use_cookie: bool,
):
    try:
        send_headers = copy(DEFAULT_HEADERS)
        if use_cookie and conf.ready_to_auth():
            send_headers["Cookie"] = conf.cookie
            send_headers["Authorization"] = conf.authorization
        url = BOOSTY_API_BASE_URL + f"/v1/blog/{creator_name}/post/{post_id}"
        logger.info("GET " + url)
        resp = await session.get(
            url,
            headers=send_headers
        )
        if resp.status != 200:
            raise Exception(f"{resp.status} on get post by id")
        result = await resp.json()
    except Exception as e:
        logger.error("Failed get posts", exc_info=e)
        result = None
    return result


async def get_post_by_id(
    creator_name: str,
    post_id: str,
    post_pool: PostPool,
    use_cookie: bool,
    offset: Optional[str] = None,
):
    logger.info(f"get posts for {creator_name}")
    async with ClientSession() as session:
        for i in range(10):
            resp = await fetch_post_by_id(
                session=session,
                creator_name=creator_name,
                post_id=post_id,
                use_cookie=use_cookie,
            )
            if not resp:
                continue

            if resp["hasAccess"]:
                new_post = Post(
                    _id=resp["id"],
                    title=resp["title"],
                    markdown_text=conf.post_text_in_markdown,
                    publish_time=resp["publishTime"]
                )
                signed_query = resp.get("signedQuery", "")
                for media in resp["data"]:
                    if media["type"] == MediaType.VIDEO.value:
                        for url in media["playerUrls"]:
                            if url["type"] in VIDEO_QUALITY.keys() and url["url"] != "":
                                new_post.media_pool.add_video(
                                    _id=media["id"],
                                    post_id=resp["id"],
                                    url=url["url"],
                                    size_amount=VIDEO_QUALITY[url["type"]],
                                    meta={"title": resp.get("title")},
                                )
                    elif media["type"] == MediaType.IMAGE.value:
                        new_post.media_pool.add_image(
                            _id=media["id"],
                            post_id=resp["id"],
                            url=media["url"],
                            width=media["width"],
                            height=media["height"]
                        )
                    elif media["type"] == MediaType.AUDIO.value:
                        new_post.media_pool.add_audio(
                            _id=media["id"],
                            post_id=resp["id"],
                            url=media["url"] + signed_query,
                            size_amount=media["size"],
                        )
                    elif media["type"] == MediaType.FILE.value:
                        new_post.media_pool.add_file(
                            _id=media["id"],
                            post_id=resp["id"],
                            url=media["url"] + signed_query,
                            size_amount=media["size"],
                            title=media["title"]
                        )
                    elif media["type"] == MediaType.TEXT.value:
                        if media["modificator"] == "":
                            new_post.add_marshaled_text(media["content"])
                        elif media["modificator"] == "BLOCK_END":
                            new_post.add_block_end()
                    elif media["type"] == MediaType.LINK.value:
                        new_post.add_link(media["content"], media["url"])
                post_pool.add_post(new_post, offset)
            post_pool.close()
            return
