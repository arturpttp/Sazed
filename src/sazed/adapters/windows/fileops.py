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

from sazed.skills.pc.fileops import ChangeBusy, ItemState, MovedAsCopy

log = logging.getLogger(__name__)

COUNT_LIMIT = 100_000
"""A folder's file count stops here (the confirmation then says "mais de 100 000")."""
_BUSY_ERRORS = {5, 32, 33}  # access denied, sharing violation, lock violation
DRIVE_FIXED = 3
RECYCLE_BIN_FOLDER = 10  # ShellSpecialFolderConstants.ssfBITBUCKET
# FOF_WANTNUKEWARNING: if Windows still cannot recycle an item, it asks instead of silently
# deleting it for good (the danger of FOF_NOCONFIRMATION alone). Values from shellcon.
FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO = 0x0004, 0x0010, 0x0040
FOF_NOERRORUI, FOF_WANTNUKEWARNING = 0x0400, 0x4000
RECYCLE_FLAGS = (
    FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI | FOF_WANTNUKEWARNING
)


def fits_in_bin(*, size: int, count: int, capacity: int | None, nuke: bool) -> bool:
    """Whether the Recycle Bin will really take an item. Windows deletes for good what does
    not fit (or when the bin is off) — under FOF_NOCONFIRMATION without even asking."""
    if nuke or capacity is None or count >= COUNT_LIMIT:
        return False  # off, unknown, or a folder too big to have been counted
    return size <= capacity


def _bin_settings(root: str) -> tuple[int | None, bool]:
    """(capacity in bytes or None when unknown, NukeOnDelete) for the drive of `root`."""
    import ctypes
    import winreg

    buf = ctypes.create_unicode_buffer(64)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if not kernel32.GetVolumeNameForVolumeMountPointW(root, buf, 64):
        return None, False
    guid = buf.value[buf.value.find("{") : buf.value.find("}") + 1]
    key_path = rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{guid}"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            megabytes = int(winreg.QueryValueEx(key, "MaxCapacity")[0])
            try:
                nuke = bool(winreg.QueryValueEx(key, "NukeOnDelete")[0])
            except OSError:
                nuke = False
    except OSError:
        return None, False
    return megabytes * 2**20, nuke


def _is_subst(drive: str) -> bool:
    import ctypes

    device = ctypes.create_unicode_buffer(512)
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.QueryDosDeviceW(drive, device, 512)
    return device.value.startswith("\\??\\")  # a subst drive maps to another path


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
    remove_copy: Callable[[str], None],
    discard_source: Callable[[str], None],
    size_of: Callable[[str], int],
    exists: Callable[[str], bool],
) -> None:
    """Move between drives without ever losing anything:

    - something already at `dst` is never touched (refused before copying);
    - a failed or incomplete copy is removed, and only the copy this call made;
    - the original goes to the Recycle Bin only after the copy is verified; if it cannot,
      `MovedAsCopy` says both now exist.
    """
    if exists(dst):
        raise FileExistsError(dst)
    try:
        copy(src, dst)
        if size_of(dst) != size_of(src):
            raise OSError(f"the copy of {src} is incomplete")
    except BaseException:
        if exists(dst):  # did not exist before: it is this call's partial copy
            try:
                remove_copy(dst)
            except OSError:
                log.exception("could not remove the partial copy %s", dst)
        raise
    try:
        discard_source(src)
    except (OSError, ChangeBusy) as error:
        raise MovedAsCopy(src) from error


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
        self._guard(
            lambda: move_across(
                src,
                dst,
                copy=_copy,
                remove_copy=_remove,
                discard_source=self._discard,
                size_of=_size,
                exists=os.path.lexists,
            )
        )

    def _discard(self, path: str) -> None:
        """The original of a cross-drive move goes to the Recycle Bin, never rmtree."""
        state = self.state(path)
        if state is None or not self.can_recycle(state):
            raise ChangeBusy(f"cannot recycle {path}")
        self.recycle(path)

    def copy(self, src: str, dst: str) -> None:
        if os.path.lexists(dst):  # lexists: a dangling link is not a free name either
            raise FileExistsError(dst)  # never overwrite: the plan chose a free name
        self._guard(lambda: _copy(src, dst))

    def rename(self, src: str, dst: str) -> None:
        self._guard(lambda: os.rename(src, dst))

    def make_folder(self, path: str) -> None:
        os.mkdir(path)  # not makedirs: a missing parent is an error, never created silently

    def can_recycle(self, item: ItemState) -> bool:
        """A fixed, non-subst drive whose bin is on and big enough for this item."""
        import ctypes

        drive = ntpath.splitdrive(os.path.abspath(item.path))[0]
        root = drive + "\\"
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if int(kernel32.GetDriveTypeW(root)) != DRIVE_FIXED or _is_subst(drive):
            return False
        capacity, nuke = _bin_settings(root)
        return fits_in_bin(size=item.size, count=item.count, capacity=capacity, nuke=nuke)

    def recycle(self, path: str) -> str:
        from win32com.shell import shell, shellcon

        result, aborted = shell.SHFileOperation(
            (0, shellcon.FO_DELETE, os.path.abspath(path), None, RECYCLE_FLAGS, None, None)
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
