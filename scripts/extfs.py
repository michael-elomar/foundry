import struct
import time
import os

# --------------------------------------------------------------------------
# EXT2
# --------------------------------------------------------------------------
EXT2_MAGIC = 0xEF53
EXT2_ROOT_INO, EXT2_FIRST_INO, INODE_SIZE = 2, 11, 128
S_IFREG, S_IFDIR, S_IFLNK = 0o100000, 0o040000, 0o120000
FT_REG, FT_DIR, FT_SYMLINK = 1, 2, 7  # file type byte in dir entries
_INODE = struct.Struct("<HHIIIIIHHIII60sIIII12x")  # 128-byte inode
_GDESC = struct.Struct("<IIIHHHH12x")  # 32-byte group descriptor
_DIRHDR = struct.Struct("<IHBB")  # inode, rec_len, name_len, type
assert _INODE.size == INODE_SIZE and _GDESC.size == 32


def _has_sb_backup(g):
    """sparse_super: backups live in groups 0, 1 and powers of 3, 5 and 7."""
    if g <= 1:
        return True
    for base in (3, 5, 7):
        n = base
        while n < g:
            n *= base
        if n == g:
            return True
    return False


class _Ext2Dir:
    """In-memory directory; laid out into blocks at close()."""

    def __init__(self, ino, parent_ino, mode, mtime):
        self.ino, self.parent_ino = ino, parent_ino
        self.mode, self.mtime = mode, mtime
        self.entries = []  # (inode, name_bytes, file_type)
        self.children = {}  # name -> _Ext2Dir (sub-directories only)
        self.names = set()  # every name in this directory (case-sensitive)
        self.min_blocks = 1


class Ext2:
    """Formats a seekable file-like object as ext2 and stores files/directories.

    Same API as Fat32. `hidden_sectors` is accepted (and ignored) so both
    classes can be constructed the same way; ext2 never stores its own offset.
    Ownership is root:root; permission bits are taken from the host files.
    """

    def __init__(self, dev, hidden_sectors=0):
        self.dev = dev
        self.formatted = False

    # ---- formatting -------------------------------------------------------
    def format(self, label="", block_size=None, bytes_per_inode=None):
        size = self.dev.size
        small = size < (512 << 20)
        bs = block_size or (1024 if small else 4096)
        if bs not in (1024, 2048, 4096):
            raise ValueError("block_size must be 1024, 2048 or 4096")
        ratio = bytes_per_inode or (4096 if small else 16384)
        fdb = 1 if bs == 1024 else 0  # first data block
        bpg = 8 * bs  # one bitmap block per group
        ipb = bs // INODE_SIZE  # inodes per block

        def geometry(blocks):
            groups = -(-(blocks - fdb) // bpg)
            ipg = -(-(blocks * bs // ratio) // groups)
            ipg = max(-(-ipg // ipb) * ipb, -(-16 // ipb) * ipb)
            ipg = min(ipg, bpg)
            return groups, ipg, ipg * INODE_SIZE // bs, -(-groups * 32 // bs)

        blocks_count = size // bs
        if blocks_count < 128:
            raise ValueError("partition too small for ext2")
        groups, ipg, itb, gdt = geometry(blocks_count)
        # Drop a runt last group that can't even hold its own metadata
        last = blocks_count - fdb - (groups - 1) * bpg
        overhead = ((1 + gdt) if _has_sb_backup(groups - 1) else 0) + 2 + itb
        if groups > 1 and last < overhead + 50:
            blocks_count = fdb + (groups - 1) * bpg
            groups, ipg, itb, gdt = geometry(blocks_count)
        if 3 + gdt + itb + 32 > min(bpg, blocks_count - fdb):
            raise ValueError("partition too small for ext2")

        self.bs, self.fdb, self.bpg = bs, fdb, bpg
        self.groups, self.ipg, self.itb, self.gdt = groups, ipg, itb, gdt
        self.blocks_count, self.inodes_count = blocks_count, groups * ipg
        self.uuid = os.urandom(16)
        self.label = os.fsencode(label)[:16]
        self.mkfs_time = int(time.time())

        # Block usage map (1 byte per block) + per-group metadata locations
        self.bused = bytearray(blocks_count)
        if fdb:
            self.bused[0] = 1  # boot block precedes group 0
            self._write(0, b"\0" * bs)
        self.gd = []  # (block_bitmap, inode_bitmap, inode_table)
        for g in range(groups):
            start = fdb + g * bpg
            bb = start + ((1 + gdt) if _has_sb_backup(g) else 0)
            ib, it = bb + 1, bb + 2
            data = it + itb
            self.bused[start:data] = b"\1" * (data - start)
            self.gd.append((bb, ib, it))
            self._write(start * bs, b"\0" * ((data - start) * bs))  # clear old junk

        self.inodes = {}  # ino -> packed 128-byte inode
        self.next_ino = EXT2_FIRST_INO
        self.cursor = 0  # next-block search position
        self.large_files = False
        self.root = _Ext2Dir(EXT2_ROOT_INO, EXT2_ROOT_INO, 0o755, self.mkfs_time)
        self.dirs = [self.root]
        self.formatted = True

        # fsck expects /lost+found (inode 11) with spare room to reconnect files
        lf = self.mkdir("/lost+found", mtime=self.mkfs_time, mode=0o700)
        lf.min_blocks = -(-16384 // bs)

    # ---- low-level helpers ---------------------------------------------
    def _write(self, off, data):
        self.dev.seek(off)
        self.dev.write(data)

    def _alloc_block(self):
        bu, c = self.bused, self.cursor
        while c < len(bu) and bu[c]:
            c += 1
        if c >= len(bu):
            raise OSError("ext2 volume full")
        bu[c] = 1
        self.cursor = c + 1
        return c

    def _alloc_ino(self):
        if self.next_ino > self.inodes_count:
            raise OSError("ext2 volume out of inodes")
        self.next_ino += 1
        return self.next_ino - 1

    def _write_data(self, blocks, data):
        """Write consecutive slices of `data` to `blocks`, merging adjacent runs."""
        bs, i = self.bs, 0
        while i < len(blocks):
            j = i
            while j + 1 < len(blocks) and blocks[j + 1] == blocks[j] + 1:
                j += 1
            self._write(blocks[i] * bs, data[i * bs : (j + 1) * bs])
            i = j + 1

    def _ptr_tree(self, blocks, level):
        """Write an (n-level) indirect block tree; return (root_block, meta_blocks)."""
        bs, ppb = self.bs, self.bs // 4
        if level == 1:
            ptrs, meta = list(blocks), 0
        else:
            span, ptrs, meta = ppb ** (level - 1), [], 0
            for i in range(0, len(blocks), span):
                b, m = self._ptr_tree(blocks[i : i + span], level - 1)
                ptrs.append(b)
                meta += m
        b = self._alloc_block()
        self._write(b * bs, struct.pack(f"<{len(ptrs)}I", *ptrs).ljust(bs, b"\0"))
        return b, meta + 1

    def _build_block_map(self, blocks):
        """Return (i_block bytes, #indirect blocks used) for a data-block list."""
        ppb = self.bs // 4
        if len(blocks) > 12 + ppb + ppb**2 + ppb**3:
            raise OSError("file too large for ext2")
        ptrs = list(blocks[:12]) + [0] * (12 - len(blocks[:12]))
        rest, meta = blocks[12:], 0
        for level in (1, 2, 3):  # single, double, triple indirect
            part, rest = rest[: ppb**level], rest[ppb**level :]
            if part:
                b, m = self._ptr_tree(part, level)
                ptrs.append(b)
                meta += m
            else:
                ptrs.append(0)
        return struct.pack("<15I", *ptrs), meta

    def _store_inode(self, ino, mode, size, mtime, nlinks, iblock, blocks512, size_high=0):
        t = int(mtime)
        self.inodes[ino] = _INODE.pack(
            mode,
            0,
            size & 0xFFFFFFFF,
            t,
            t,
            t,
            0,
            0,
            nlinks,
            blocks512,
            0,
            0,
            iblock,
            0,
            0,
            size_high,
            0,
        )

    # ---- directories --------------------------------------------------------
    @staticmethod
    def _parts(path):
        return [p for p in path.replace("\\", "/").split("/") if p]

    @staticmethod
    def _check_name(d, name):
        nb = os.fsencode(name)
        if not 0 < len(nb) <= 255 or name in (".", "..") or b"\0" in nb:
            raise ValueError(f"invalid ext2 file name: {name!r}")
        if name in d.names:
            raise FileExistsError(name)
        return nb

    def mkdir(self, path, mtime=None, mode=0o755):
        """Create directory `path` (and any missing parents); return its _Ext2Dir."""
        assert self.formatted, "call format() first"
        mtime = time.time() if mtime is None else mtime
        cur = self.root
        for part in self._parts(path):
            if part in cur.children:
                cur = cur.children[part]
                continue
            nb = self._check_name(cur, part)  # also catches file clash
            new = _Ext2Dir(self._alloc_ino(), cur.ino, mode, mtime)
            cur.entries.append((new.ino, nb, FT_DIR))
            cur.names.add(part)
            cur.children[part] = new
            self.dirs.append(new)
            cur = new
        return cur

    def _layout_dir(self, d):
        """Pack directory entries into blocks; the last entry of a block
        stretches (rec_len) to the end of that block."""
        bs = self.bs
        ents = [(d.ino, b".", FT_DIR), (d.parent_ino, b"..", FT_DIR)] + d.entries
        blocks, cur, used = [], [], 0

        def flush():
            out = bytearray()
            for i, (ino, nm, ft) in enumerate(cur):
                pad = (len(nm) + 3) & ~3
                rec = bs - len(out) if i == len(cur) - 1 else 8 + pad
                out += _DIRHDR.pack(ino, rec, len(nm), ft)
                out += nm.ljust(pad, b"\0")
            blocks.append(bytes(out.ljust(bs, b"\0")))

        for e in ents:
            rec = 8 + ((len(e[1]) + 3) & ~3)
            if used + rec > bs:
                flush()
                cur.clear()
                used = 0
            cur.append(e)
            used += rec
        flush()
        while len(blocks) < d.min_blocks:  # empty dir blocks
            blocks.append(_DIRHDR.pack(0, bs, 0, 0).ljust(bs, b"\0"))
        return blocks

    # ---- public API ---------------------------------------------------------
    def add_file(self, src, dest=None):
        """Copy host file `src` to image path `dest` (default: root, same name).

        Missing parent directories of `dest` are created automatically.
        """
        assert self.formatted, "call format() first"
        st = os.stat(src)
        parts = self._parts(dest if dest is not None else os.path.basename(src))
        if not parts:
            raise ValueError("empty destination path")
        parent = self.mkdir("/".join(parts[:-1]), mtime=st.st_mtime)
        nb = self._check_name(parent, parts[-1])  # fail before touching blocks

        bs, blocks, size = self.bs, [], 0
        with open(src, "rb") as f:
            while chunk := f.read(1 << 20):  # 1 MiB, a multiple of bs
                n = -(-len(chunk) // bs)
                new = [self._alloc_block() for _ in range(n)]
                self._write_data(new, chunk.ljust(n * bs, b"\0"))
                blocks += new
                size += len(chunk)
        iblock, meta = self._build_block_map(blocks)
        if size >= 1 << 31:
            self.large_files = True
        ino = self._alloc_ino()
        self._store_inode(
            ino,
            S_IFREG | (st.st_mode & 0o7777),
            size,
            st.st_mtime,
            1,
            iblock,
            (len(blocks) + meta) * (bs // 512),
            size >> 32,
        )
        parent.entries.append((ino, nb, FT_REG))
        parent.names.add(parts[-1])

    def add_symlink(self, target, dest, mtime=None):
        """Create a symbolic link at `dest` pointing to `target` (a string)."""
        assert self.formatted, "call format() first"
        parts = self._parts(dest)
        if not parts:
            raise ValueError("empty destination path")
        mtime = time.time() if mtime is None else mtime
        parent = self.mkdir("/".join(parts[:-1]), mtime=mtime)
        nb = self._check_name(parent, parts[-1])
        tb, bs = os.fsencode(target), self.bs
        if len(tb) < 60:  # "fast" symlink: target lives in i_block
            iblock, nsect = tb.ljust(60, b"\0"), 0
        elif len(tb) <= bs:  # "slow" symlink: one data block
            b = self._alloc_block()
            self._write(b * bs, tb.ljust(bs, b"\0"))
            iblock, nsect = struct.pack("<15I", b, *[0] * 14), bs // 512
        else:
            raise ValueError("symlink target too long")
        ino = self._alloc_ino()
        self._store_inode(ino, S_IFLNK | 0o777, len(tb), mtime, 1, iblock, nsect)
        parent.entries.append((ino, nb, FT_SYMLINK))
        parent.names.add(parts[-1])

    def add_tree(self, src_dir, dest="/"):
        """Recursively copy host directory `src_dir` to image path `dest`,
        preserving the tree structure, permission bits and symlinks."""
        st = os.stat(src_dir)
        d = self.mkdir(dest, mtime=st.st_mtime, mode=st.st_mode & 0o7777)
        prefix = dest.rstrip("/")
        for e in sorted(os.scandir(src_dir), key=lambda e: e.name):
            target = f"{prefix}/{e.name}"
            if e.is_symlink():
                self.add_symlink(
                    os.readlink(e.path), target, mtime=e.stat(follow_symlinks=False).st_mtime
                )
            elif e.is_dir():
                self.add_tree(e.path, target)
            elif e.is_file():
                self.add_file(e.path, target)
        return d

    def close(self):
        """Write directories, inode tables, bitmaps, group descriptors, superblocks."""
        bs, ipg = self.bs, self.ipg
        for d in self.dirs:  # 1. directory contents
            raw = self._layout_dir(d)
            blks = [self._alloc_block() for _ in raw]
            self._write_data(blks, b"".join(raw))
            iblock, meta = self._build_block_map(blks)
            self._store_inode(
                d.ino,
                S_IFDIR | d.mode,
                len(blks) * bs,
                d.mtime,
                2 + len(d.children),
                iblock,
                (len(blks) + meta) * (bs // 512),
            )

        for ino, raw in self.inodes.items():  # 2. inode tables
            g, idx = divmod(ino - 1, ipg)
            self._write(self.gd[g][2] * bs + idx * INODE_SIZE, raw)

        gdesc, tot_fb, tot_fi = [], 0, 0  # 3. bitmaps + descriptors
        for g in range(self.groups):
            start = self.fdb + g * self.bpg
            n = min(self.bpg, self.blocks_count - start)
            used = self.bused[start : start + n]
            bm = bytearray(bs)
            for i, u in enumerate(used):
                if u:
                    bm[i >> 3] |= 1 << (i & 7)
            for i in range(n, bs * 8):  # padding bits past group end
                bm[i >> 3] |= 1 << (i & 7)
            used_i = max(0, min(ipg, self.next_ino - 1 - g * ipg))
            im = bytearray(bs)
            for i in range(used_i):
                im[i >> 3] |= 1 << (i & 7)
            im[ipg // 8 :] = b"\xff" * (bs - ipg // 8)
            bb, ib, _ = self.gd[g]
            self._write(bb * bs, bytes(bm))
            self._write(ib * bs, bytes(im))
            free_b, free_i = used.count(0), ipg - used_i
            ndirs = sum(1 for d in self.dirs if (d.ino - 1) // ipg == g)
            gdesc.append(_GDESC.pack(*self.gd[g], free_b, free_i, ndirs, 0))
            tot_fb += free_b
            tot_fi += free_i
        gdt_bytes = b"".join(gdesc).ljust(self.gdt * bs, b"\0")

        for g in range(self.groups):  # 4. superblock + GDT (+backups)
            if not _has_sb_backup(g):
                continue
            start = self.fdb + g * self.bpg
            self._write(1024 if g == 0 else start * bs, self._superblock(g, tot_fb, tot_fi))
            self._write((start + 1) * bs, gdt_bytes)

    def _superblock(self, group, free_blocks, free_inodes):
        sb, now = bytearray(1024), int(time.time())
        lg = {1024: 0, 2048: 1, 4096: 2}[self.bs]
        struct.pack_into(
            "<13IHhHHHHIIIIHH",
            sb,
            0,
            self.inodes_count,
            self.blocks_count,
            0,
            free_blocks,
            free_inodes,
            self.fdb,
            lg,
            lg,
            self.bpg,
            self.bpg,
            self.ipg,
            0,
            now,  # last mount time, last write time
            0,
            -1,
            EXT2_MAGIC,
            1,
            1,
            0,  # mnt count, max mnt, magic, state, errors, minor
            now,
            0,
            0,
            1,
            0,
            0,
        )  # lastcheck, interval, OS=Linux, rev 1, resuid/gid
        ro_compat = 0x1 | (0x2 if self.large_files else 0)  # sparse_super [+ large_file]
        struct.pack_into(
            "<IHHIII", sb, 84, EXT2_FIRST_INO, INODE_SIZE, group, 0, 0x2, ro_compat
        )  # incompat 0x2 = dir file types
        sb[104:120] = self.uuid
        sb[120:136] = self.label.ljust(16, b"\0")
        struct.pack_into("<I", sb, 264, self.mkfs_time)
        return bytes(sb)
