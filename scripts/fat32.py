import string
import struct
import os
import time

from utils import *

# --------------------------------------------------------------------------
# FAT32
# --------------------------------------------------------------------------
EOC = 0x0FFFFFFF
_SHORT_OK = set(string.ascii_uppercase + string.digits + "!#$%&'()-@^_`{}~")
_NAME_BAD = set('"*/:<>?\\|')
ATTR_ARCHIVE, ATTR_DIR = 0x20, 0x10
_DIRENT = "<11sBBBHHHHHHHI"


def _lfn_checksum(short11):
    s = 0
    for b in short11:
        s = (((s & 1) << 7) + (s >> 1) + b) & 0xFF
    return s


def _fat_time(mtime):
    t = time.localtime(max(mtime, 315532800))  # FAT epoch is 1980-01-01
    date = ((t.tm_year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2), date


def _ceil_div(a, b):
    return -(-a // b)


class _Dir:
    """In-memory directory: raw 32-byte entries plus its own name namespace."""

    def __init__(self, cluster, parent_cluster, entries=b""):
        self.cluster = cluster
        self.parent_cluster = parent_cluster
        self.entries = bytearray(entries)
        self.names = set()  # lower-case long names (duplicate detection)
        self.shorts = set()  # 11-byte short names in use
        self.children = {}  # lower-case name -> _Dir


class Fat32:
    """Formats a seekable file-like object as FAT32 and stores files/directories.

    `dev` needs .seek/.write/.size (OffsetFile works).
    `hidden_sectors` should equal the partition's start LBA from the MBR.
    """

    def __init__(self, dev, hidden_sectors=0):
        self.dev = dev
        self.hidden = hidden_sectors
        self.formatted = False

    # ---- formatting -------------------------------------------------------
    def format(self, label="NO NAME", oem=b"PYFAT32 ", volume_id=0x1234ABCD):
        total = self.dev.size // SECTOR_SIZE
        reserved, nfats = 32, 2

        # Pick the largest cluster size that still leaves >= 65525 clusters,
        # otherwise the volume would legally be FAT16, not FAT32.
        for spc in (128, 64, 32, 16, 8, 4, 2, 1):
            fatsz = 1
            while True:
                clusters = (total - reserved - nfats * fatsz) // spc
                needed_fatsz = _ceil_div((clusters + 2) * 4, SECTOR_SIZE)
                if needed_fatsz <= fatsz:
                    break
                fatsz = needed_fatsz
            if clusters >= 65525:
                break
        else:
            raise ValueError("partition too small for FAT32")

        self.total, self.reserved, self.nfats = total, reserved, nfats
        self.spc, self.fatsz, self.clusters = spc, fatsz, clusters
        self.cluster_bytes = spc * SECTOR_SIZE
        self.data_start = reserved + nfats * fatsz  # in sectors

        # In-memory FAT: [0]=media, [1]=clean flags, [2]=root dir (end of chain)
        self.fat = [0] * (clusters + 2)
        self.fat[0], self.fat[1], self.fat[2] = 0x0FFFFFF8, EOC, EOC
        self.next_free = 3
        self.root = _Dir(2, 0)
        self.dirs = [self.root]  # every directory, flushed in close()

        # FAT32 stores the volume label twice: in the BPB and as a root entry
        lbl = label.upper().encode("ascii", "replace")[:11].ljust(11)
        ftime, fdate = _fat_time(time.time())
        self.root.entries += struct.pack(
            _DIRENT, lbl, 0x08, 0, 0, ftime, fdate, fdate, 0, ftime, fdate, 0, 0
        )

        # Boot sector with BPB
        bs = bytearray(SECTOR_SIZE)
        bs[0:3] = b"\xeb\x58\x90"
        bs[3:11] = oem[:8].ljust(8)
        struct.pack_into(
            "<HBHBHHBHHHII",
            bs,
            11,
            SECTOR_SIZE,
            spc,
            reserved,
            nfats,
            0,
            0,
            0xF8,
            0,
            63,
            255,
            self.hidden,
            total,
        )
        struct.pack_into("<IHHIHH", bs, 36, fatsz, 0, 0, 2, 1, 6)
        bs[64] = 0x80
        bs[66] = 0x29
        struct.pack_into("<I", bs, 67, volume_id)
        bs[71:82] = label.upper().encode("ascii", "replace")[:11].ljust(11)
        bs[82:90] = b"FAT32   "
        bs[510:512] = b"\x55\xaa"
        self.boot_sector = bytes(bs)

        # Zero the reserved area (the image may contain old garbage)
        self._write(0, b"\0" * (reserved * SECTOR_SIZE))
        self.formatted = True

    # ---- low-level helpers ---------------------------------------------
    def _write(self, off, data):
        self.dev.seek(off)
        self.dev.write(data)

    def _cluster_off(self, c):
        return (self.data_start + (c - 2) * self.spc) * SECTOR_SIZE

    def _alloc(self, n):
        """Allocate n contiguous clusters, link them in the FAT, return first."""
        first = self.next_free
        if first + n > len(self.fat):
            raise OSError("FAT32 volume full")
        for c in range(first, first + n):
            self.fat[c] = c + 1 if c < first + n - 1 else EOC
        self.next_free += n
        return first

    # ---- directory entries ------------------------------------------------
    @staticmethod
    def _check_name(d, name):
        if (
            not name
            or name in (".", "..")
            or len(name) > 255
            or any(c in _NAME_BAD or ord(c) < 32 for c in name)
        ):
            raise ValueError(f"invalid FAT file name: {name!r}")
        if name.lower() in d.names:
            raise FileExistsError(name)

    @staticmethod
    def _short_name(d, name):
        """Return (short11_bytes, needs_lfn), unique within directory d."""
        base, ext = name.rsplit(".", 1) if "." in name else (name, "")
        exact = (
            name == name.upper()
            and 1 <= len(base) <= 8
            and len(ext) <= 3
            and name.count(".") <= 1
            and all(c in _SHORT_OK for c in base + ext)
        )
        if exact:
            return (base.ljust(8) + ext.ljust(3)).encode("ascii"), False

        def clean(s):
            return "".join(
                c if c in _SHORT_OK else "_" for c in s.upper().replace(" ", "").replace(".", "")
            )

        b, e = clean(base) or "_", clean(ext)[:3]
        for n in range(1, 1000000):
            tail = f"~{n}"
            short = ((b[: 8 - len(tail)] + tail).ljust(8) + e.ljust(3)).encode("ascii")
            if short not in d.shorts:
                return short, True
        raise OSError("cannot generate short name")

    def _add_entry(self, d, name, first_cluster, size, mtime, attr):
        """Append [LFN entries +] short entry for `name` to directory d."""
        self._check_name(d, name)
        short, lfn = self._short_name(d, name)
        d.names.add(name.lower())
        d.shorts.add(short)

        out = b""
        if lfn:
            raw = name.encode("utf-16-le")
            chars = list(struct.unpack(f"<{len(raw) // 2}H", raw))
            if len(chars) % 13:
                chars.append(0)
            chars += [0xFFFF] * (-len(chars) % 13)
            n = len(chars) // 13
            ck = _lfn_checksum(short)
            for i in range(n, 0, -1):  # last LFN part is stored first
                p = chars[(i - 1) * 13 : i * 13]
                seq = i | (0x40 if i == n else 0)
                out += struct.pack(
                    "<B5HBBB6HH2H", seq, *p[0:5], 0x0F, 0, ck, *p[5:11], 0, *p[11:13]
                )

        ftime, fdate = _fat_time(mtime)
        out += struct.pack(
            _DIRENT,
            short,
            attr,
            0,
            0,
            ftime,
            fdate,
            fdate,
            first_cluster >> 16,
            ftime,
            fdate,
            first_cluster & 0xFFFF,
            size,
        )
        d.entries += out

    @staticmethod
    def _dot_entries(cluster, parent_cluster, mtime):
        """'.' and '..' entries that begin every non-root directory."""
        ftime, fdate = _fat_time(mtime)

        def ent(name, c):
            return struct.pack(
                _DIRENT,
                name.ljust(11),
                ATTR_DIR,
                0,
                0,
                ftime,
                fdate,
                fdate,
                c >> 16,
                ftime,
                fdate,
                c & 0xFFFF,
                0,
            )

        return ent(b".", cluster) + ent(b"..", parent_cluster)

    # ---- public API ---------------------------------------------------------
    @staticmethod
    def _parts(path):
        return [p for p in path.replace("\\", "/").split("/") if p]

    def mkdir(self, path, mtime=None):
        """Create directory `path` (and any missing parents); return its _Dir."""
        assert self.formatted, "call format() first"
        mtime = time.time() if mtime is None else mtime
        cur = self.root
        for part in self._parts(path):
            key = part.lower()
            if key in cur.children:
                cur = cur.children[key]
                continue
            self._check_name(cur, part)  # also catches file clash
            c = self._alloc(1)  # first cluster of new dir
            parent = 0 if cur is self.root else cur.cluster  # spec: root is 0
            new = _Dir(c, parent, self._dot_entries(c, parent, mtime))
            self._add_entry(cur, part, c, 0, mtime, ATTR_DIR)
            cur.children[key] = new
            self.dirs.append(new)
            cur = new
        return cur

    def add_file(self, src, dest=None):
        """Copy host file `src` to image path `dest` (default: root, same name).

        Missing parent directories of `dest` are created automatically.
        """
        assert self.formatted, "call format() first"
        st = os.stat(src)
        size = st.st_size
        if size >= 1 << 32:
            raise ValueError("FAT32 files must be < 4 GiB")
        parts = self._parts(dest if dest is not None else os.path.basename(src))
        if not parts:
            raise ValueError("empty destination path")
        parent = self.mkdir("/".join(parts[:-1]), mtime=st.st_mtime)
        name = parts[-1]
        self._check_name(parent, name)  # fail before touching any clusters

        cb = self.cluster_bytes
        ncl = -(-size // cb)
        first = self._alloc(ncl) if ncl else 0  # empty files own no clusters
        if ncl:
            self.dev.seek(self._cluster_off(first))
            written = 0
            with open(src, "rb") as f:
                while chunk := f.read(1 << 20):
                    self.dev.write(chunk)
                    written += len(chunk)
            pad = ncl * cb - written  # zero-fill the last cluster
            if pad:
                self.dev.write(b"\0" * pad)
        self._add_entry(parent, name, first, size, st.st_mtime, ATTR_ARCHIVE)

    def add_tree(self, src_dir, dest="/"):
        """Recursively copy host directory `src_dir` to image path `dest`,
        preserving the tree structure. Symlinks are skipped (FAT has none)."""
        d = self.mkdir(dest, mtime=os.stat(src_dir).st_mtime)
        prefix = dest.rstrip("/")
        for e in sorted(os.scandir(src_dir), key=lambda e: e.name):
            if e.is_symlink():
                continue
            target = f"{prefix}/{e.name}"
            if e.is_dir():
                self.add_tree(e.path, target)
            elif e.is_file():
                self.add_file(e.path, target)
        return d

    def close(self):
        """Write all directories, both FATs, FSInfo and the backup boot sector."""
        cb = self.cluster_bytes
        for d in self.dirs:
            data = bytes(d.entries)
            if len(data) > 65536 * 32:
                raise OSError("directory has too many entries")
            chain = [d.cluster]
            for _ in range(max(1, -(-len(data) // cb)) - 1):  # grow if needed
                c = self._alloc(1)
                self.fat[chain[-1]] = c
                chain.append(c)
            for i, c in enumerate(chain):
                chunk = data[i * cb : (i + 1) * cb].ljust(cb, b"\0")
                self._write(self._cluster_off(c), chunk)

        fat_bytes = struct.pack(f"<{len(self.fat)}I", *self.fat)
        fat_bytes = fat_bytes.ljust(self.fatsz * SECTOR_SIZE, b"\0")
        for i in range(self.nfats):
            self._write((self.reserved + i * self.fatsz) * SECTOR_SIZE, fat_bytes)

        free = self.clusters - (self.next_free - 2)
        fsinfo = bytearray(SECTOR_SIZE)
        struct.pack_into("<I", fsinfo, 0, 0x41615252)
        struct.pack_into("<I", fsinfo, 484, 0x61417272)
        struct.pack_into("<II", fsinfo, 488, free, self.next_free)
        fsinfo[510:512] = b"\x55\xaa"
        for base in (0, 6):  # primary and backup copies
            self._write(base * SECTOR_SIZE, self.boot_sector)
            self._write((base + 1) * SECTOR_SIZE, bytes(fsinfo))
