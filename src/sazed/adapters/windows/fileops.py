"""File changes on Windows: standard file calls, and the Recycle Bin through the shell.

Never overwrites, never deletes permanently: a delete is always a Recycle Bin move, and a move
to another drive copies, verifies the size, and only then removes the original.
"""

from __future__ import annotations

import json
import logging
import ntpath
import os
import shutil
from collections.abc import Callable
from datetime import datetime

from sazed.skills.pc.fileops import ChangeBusy, ItemState

log = logging.getLogger(__name__)

COUNT_LIMIT = 100_000
"""A folder's file count stops here (the confirmation then says "mais de 100 000")."""
_BUSY_ERRORS = {5, 32, 33}  # access denied, sharing violation, lock violation
DRIVE_FIXED = 3
RECYCLE_BIN_FOLDER = 10  # ShellSpecialFolderConstants.ssfBITBUCKET


def count_tree(path: str, limit: int = COUNT_LIMIT) -> tuple[int, int]:
    """(files, total bytes) under `path`, stopping after `limit` files."""
    files = size = 0
    stack = [path]
    while stack and files < limit:
        try:
            with os.scandir(stack.pop()) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        files += 1
                        size += entry.stat(follow_symlinks=False).st_size
                        if files >= limit:
                            break
        except OSError:
            continue  # an unreadable subfolder is left out of the count
    return files, size


def move_across(
    src: str,
    dst: str,
    *,
    copy: Callable[[str, str], None],
    remove: Callable[[str], None],
    size_of: Callable[[str], int],
) -> None:
    """Move between drives: copy, verify, remove. On any failure the original stays and the
    partial copy goes."""
    try:
        copy(src, dst)
        if size_of(dst) != size_of(src):
            raise OSError(f"the copy of {src} is incomplete")
    except BaseException:
        try:
            remove(dst)
        except OSError:
            log.exception("could not remove the partial copy %s", dst)
        raise
    remove(src)


def _busy(error: OSError) -> bool:
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in _BUSY_ERRORS


def _remove(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def _size(path: str) -> int:
    return count_tree(path)[1] if os.path.isdir(path) else os.path.getsize(path)


def _copy(src: str, dst: str) -> None:
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


class WindowsFileChanger:
    def state(self, path: str) -> ItemState | None:
        try:
            info = os.stat(path)
        except OSError:
            return None
        if os.path.isdir(path):
            count, size = count_tree(path)
            return ItemState(path, True, size, info.st_mtime, count)
        return ItemState(path, False, info.st_size, info.st_mtime, 0)

    def names_in(self, folder: str) -> set[str]:
        try:
            return set(os.listdir(folder))
        except OSError:
            return set()

    def _guard(self, action: Callable[[], None]) -> None:
        try:
            action()
        except OSError as error:
            if _busy(error):
                raise ChangeBusy(str(error)) from error
            raise

    def move(self, src: str, dst: str) -> None:
        same_drive = ntpath.splitdrive(src)[0].lower() == ntpath.splitdrive(dst)[0].lower()
        if same_drive:
            self._guard(lambda: os.rename(src, dst))
            return
        self._guard(lambda: move_across(src, dst, copy=_copy, remove=_remove, size_of=_size))

    def copy(self, src: str, dst: str) -> None:
        if os.path.exists(dst):
            raise FileExistsError(dst)  # never overwrite: the plan chose a free name
        self._guard(lambda: _copy(src, dst))

    def rename(self, src: str, dst: str) -> None:
        self._guard(lambda: os.rename(src, dst))

    def make_folder(self, path: str) -> None:
        os.mkdir(path)  # not makedirs: a missing parent is an error, never created silently

    def can_recycle(self, path: str) -> bool:
        import ctypes

        root = ntpath.splitdrive(os.path.abspath(path))[0] + "\\"
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        return int(kernel32.GetDriveTypeW(root)) == DRIVE_FIXED

    def recycle(self, path: str) -> str:
        from win32com.shell import shell, shellcon

        flags = (
            shellcon.FOF_ALLOWUNDO
            | shellcon.FOF_NOCONFIRMATION
            | shellcon.FOF_SILENT
            | shellcon.FOF_NOERRORUI
        )
        result, aborted = shell.SHFileOperation(
            (0, shellcon.FO_DELETE, os.path.abspath(path), None, flags, None, None)
        )
        if result != 0 or aborted or os.path.exists(path):
            raise ChangeBusy(f"could not recycle {path} (code {result})")
        return json.dumps({"path": os.path.abspath(path), "at": datetime.now().isoformat()})

    def restore(self, ref: str) -> bool:
        import pythoncom
        import win32com.client

        wanted = json.loads(ref)
        original = os.path.normcase(wanted["path"])
        folder, name = ntpath.split(original)
        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.Namespace(RECYCLE_BIN_FOLDER)
            stem = ntpath.splitext(name)[0]
            deleted_at = datetime.fromisoformat(wanted["at"]).timestamp()
            matches = []
            for item in bin_folder.Items():
                deleted_from = str(item.ExtendedProperty("System.Recycle.DeletedFrom") or "")
                item_name = str(bin_folder.GetDetailsOf(item, 0) or item.Name)
                if os.path.normcase(deleted_from) != folder:
                    continue
                if os.path.normcase(item_name) not in (name, stem):
                    continue
                when = item.ExtendedProperty("System.Recycle.DateDeleted")
                gap = abs(when.timestamp() - deleted_at) if when is not None else float("inf")
                matches.append((gap, item))
            if not matches:
                return False
            # The same name may be in the bin more than once: take the one this change deleted.
            min(matches, key=lambda gi: gi[0])[1].InvokeVerb("undelete")
            return os.path.exists(wanted["path"])
        finally:
            pythoncom.CoUninitialize()
