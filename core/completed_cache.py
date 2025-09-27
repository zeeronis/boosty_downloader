from pathlib import Path


class CompletedCache:
    def __init__(self, cache_path: Path):
        self.completed_dir = cache_path / "completed"
        self.completed_dir.mkdir(exist_ok=True)

    def add(self, post_id: str, file_id: str):
        post_dir = self.completed_dir / post_id
        post_dir.mkdir(exist_ok=True)
        cache_file = post_dir / file_id
        cache_file.touch()

    def check(self, post_id: str, file_id: str) -> bool:
        cache_file = self.completed_dir / post_id / file_id
        return cache_file.exists()