from pathlib import Path
from typing import Optional, Tuple

import aiofiles


class DownloadState:
    def __init__(self, state_file_path: Path):
        self.state_file_path = state_file_path

    async def create(self, url: str, file_path: Path):
        async with aiofiles.open(self.state_file_path, "w") as f:
            await f.write(f"{url}\n{file_path}")

    async def read(self) -> Optional[Tuple[str, Path]]:
        if not self.state_file_path.exists():
            return None
        async with aiofiles.open(self.state_file_path, "r") as f:
            lines = await f.readlines()
            if len(lines) != 2:
                return None
            return lines[0].strip(), Path(lines[1].strip())

    async def remove(self):
        if self.state_file_path.exists():
            self.state_file_path.unlink()