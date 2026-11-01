import hashlib
import os
import tempfile
from unittest import TestCase

import pycdlib
from pycdlib import pycdlibexception

from turbostage import iso_utils, utils

BLOCK = 2048
FLAG_DIRECTORY = 0x02
FLAG_PROTECTION = 0x10


def _both_endian(value: int, size: int) -> bytes:
    return value.to_bytes(size, "little") + value.to_bytes(size, "big")


def _record(name: bytes, extent: int, size: int, flags: int, xattr_len: int = 1) -> bytes:
    body = (
        bytes([xattr_len])
        + _both_endian(extent, 4)
        + _both_endian(size, 4)
        + bytes([96, 1, 1, 0, 0, 0, 0])  # recording date
        + bytes([flags, 0, 0])
        + _both_endian(1, 2)  # volume sequence number
        + bytes([len(name)])
        + name
    )
    if len(body) % 2 == 0:  # records have an even length
        body += b"\x00"
    return bytes([len(body) + 1]) + body


def make_xattr_iso(path: str, root_files: dict[bytes, bytes], sub_files: dict[bytes, bytes]) -> None:
    """Write an ISO like 1990s mastering tools did: every record has a
    one-block extended attribute record and the protection flag."""
    flags_file, flags_dir = FLAG_PROTECTION, FLAG_PROTECTION | FLAG_DIRECTORY
    next_block = 18
    blocks: dict[int, bytes] = {}

    def allocate(data: bytes) -> int:
        """Store data after a one-block extended attribute record; return the extent."""
        nonlocal next_block
        extent = next_block
        blocks[extent] = b"\x00" * BLOCK  # extended attribute record
        blocks[extent + 1] = data
        next_block += 1 + max(1, -(-len(data) // BLOCK))
        return extent

    root_extent, sub_extent = next_block, next_block + 2
    next_block += 4
    root_file_records = [_record(n, allocate(d), len(d), flags_file) for n, d in root_files.items()]
    sub_file_records = [_record(n, allocate(d), len(d), flags_file) for n, d in sub_files.items()]

    sub_dir = _record(b"\x00", sub_extent, BLOCK, flags_dir) + _record(b"\x01", root_extent, BLOCK, flags_dir)
    blocks[sub_extent] = b"\x00" * BLOCK
    blocks[sub_extent + 1] = sub_dir + b"".join(sub_file_records)
    root_dir = (
        _record(b"\x00", root_extent, BLOCK, flags_dir)
        + _record(b"\x01", root_extent, BLOCK, flags_dir)
        + _record(b"SUB", sub_extent, BLOCK, flags_dir)
        + b"".join(root_file_records)
    )
    blocks[root_extent] = b"\x00" * BLOCK
    blocks[root_extent + 1] = root_dir

    pvd = bytearray(BLOCK)
    pvd[0:7] = b"\x01CD001\x01"
    pvd[8:72] = b" " * 32 + b"XATTRTEST".ljust(32)
    pvd[80:88] = _both_endian(next_block, 4)
    pvd[120:124] = _both_endian(1, 2)
    pvd[124:128] = _both_endian(1, 2)
    pvd[128:132] = _both_endian(BLOCK, 2)
    pvd[156:190] = _record(b"\x00", root_extent, BLOCK, flags_dir)
    pvd[190:813] = b" " * 623
    for offset in (813, 830, 847, 864):  # creation/modification/expiration/effective dates
        pvd[offset : offset + 17] = b"0" * 16 + b"\x00"
    pvd[881] = 1
    blocks[16] = bytes(pvd)
    blocks[17] = b"\xffCD001\x01".ljust(BLOCK, b"\x00")  # volume descriptor set terminator

    image = bytearray(next_block * BLOCK)
    for block, data in blocks.items():  # data may span several blocks
        image[block * BLOCK : block * BLOCK + len(data)] = data
    with open(path, "wb") as f:
        f.write(image)


class TestIsoWithExtendedAttributes(TestCase):
    GAME = b"MZ" + bytes(range(256)) * 20  # spans several blocks
    SETUP = b"MZ setup"
    DATA = b"level data" * 1000

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".iso")
        os.close(fd)
        self.addCleanup(os.unlink, self.path)
        make_xattr_iso(
            self.path,
            {b"GAME.EXE;1": self.GAME, b"README.TXT;1": b"hello"},
            {b"SETUP.EXE;1": self.SETUP, b"LEVELS.DAT;1": self.DATA},
        )

    def test_pycdlib_rejects_this_image(self):
        # The premise of the fallback: if pycdlib ever accepts these images,
        # this test tells us the basic reader is no longer exercised here.
        iso = pycdlib.PyCdlib()
        with self.assertRaisesRegex(pycdlibexception.PyCdlibInvalidISO, "Extended Attributes"):
            iso.open(self.path)

    def test_detected_as_iso_with_label(self):
        self.assertEqual(iso_utils.get_archive_type(self.path), "iso")
        self.assertEqual(iso_utils.get_iso_volume_label(self.path), "XATTRTEST")

    def test_lists_files_in_all_directories(self):
        self.assertEqual(
            sorted(iso_utils.list_files_in_iso(self.path)),
            ["/GAME.EXE", "/README.TXT", "/SUB/LEVELS.DAT", "/SUB/SETUP.EXE"],
        )
        self.assertEqual(sorted(iso_utils.list_executables_in_iso(self.path)), ["/GAME.EXE", "/SUB/SETUP.EXE"])

    def test_hashes_skip_the_extended_attribute_record(self):
        md5 = lambda data: hashlib.md5(data).hexdigest()  # noqa: E731
        self.assertEqual(
            iso_utils.compute_hash_for_largest_files_in_iso(self.path, 2),
            [("/SUB/LEVELS.DAT", len(self.DATA), md5(self.DATA)), ("/GAME.EXE", len(self.GAME), md5(self.GAME))],
        )
        self.assertEqual(
            sorted(iso_utils.compute_hashes_for_executables_in_iso(self.path)),
            [("/GAME.EXE", 0, md5(self.GAME)), ("/SUB/SETUP.EXE", 0, md5(self.SETUP))],
        )

    def test_library_scan_can_identify_it(self):
        archive_type, hashes = utils.hash_archive_top(self.path, 4)
        self.assertEqual(archive_type, "iso")
        self.assertEqual(len(hashes), 4)

    def test_not_an_iso_still_fails(self):
        with open(self.path, "r+b") as f:
            f.seek(16 * BLOCK + 1)
            f.write(b"XXXXX")
        with self.assertRaises(Exception):
            iso_utils.list_files_in_iso(self.path)
