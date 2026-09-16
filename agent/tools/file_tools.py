import os
import shutil


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def create_file(path: str, content: str) -> None:
    if os.path.exists(path):
        raise FileExistsError(f"File already exists: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_file(path: str, content: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def overwrite_file(path: str, content: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File does not exist: {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def delete_file(path: str) -> None:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File does not exist: {path}")
    os.remove(path)


def delete_dir(path: str) -> None:
    if not os.path.isdir(path):
        raise NotADirectoryError(f"Directory does not exist: {path}")
    shutil.rmtree(path)


def move_file(src: str, dest: str) -> None:
    if not os.path.exists(src):
        raise FileNotFoundError(f"Source does not exist: {src}")
    shutil.move(src, dest)
