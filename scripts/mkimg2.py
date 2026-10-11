#!/usr/bin/env python3
"""
mkimg.py - build FAT32 and ext2 filesystem images from scratch, pure Python.

    python3 mkimg.py fat32 disk.img 64M --label MYDISK --populate ./staging
    python3 mkimg.py ext2  disk.img 64M --label data --populate ./staging [--block-size 4096]

Images are sparse files: only metadata and file data are actually written.
--populate copies a staging directory (files, subdirectories and, on ext2,
symlinks) into the new filesystem.
"""

import argparse
import os
import random
import shutil
import struct
import time
import uuid

KiB, MiB, GiB = 1 << 10, 1 << 20, 1 << 30


def parse_size(text):
    units = {"K": KiB, "M": MiB, "G": GiB}
    text = text.strip().upper().rstrip("B").rstrip("I")
    if text and text[-1] in units:
        return int(float(text[:-1]) * units[text[-1]])
    return int(text)


# ───────────────────────────── FAT32 ─────────────────────────────

FAT_OK = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$%'-_@~`!(){}^#&")
BAD_NAME_CHARS = set('\\/:*?"<>|')


def fat_stamp(ts):
    """Unix time -> (FAT date, FAT time)."""
    t = time.localtime(ts)
    year = min(max(t.tm_year, 1980), 2107)
    date = ((year - 1980) << 9) | (t.tm_mon << 5) | t.tm_mday
    return date, (t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2)


def fat_is_short(name):
    """True if the name is already a legal upper-case 8.3 name (no LFN needed)."""
    base, dot, ext = name.partition(".")
    return (
        1 <= len(base) <= 8
        and len(ext) <= 3
        and (ext or not dot)
        and all(c in FAT_OK for c in base + ext)
    )


def fat_alias(name, taken):
    """Generate a unique 8.3 alias such as 'README~1.MAR' (as an 11-char string)."""
    stem, dot, ext = name.upper().lstrip(". ").rpartition(".")
    if not dot:
        stem, ext = ext, ""

    def clean(s):
        s = s.replace(" ", "").replace(".", "")
        return "".join(c if c in FAT_OK else "_" for c in s)

    stem, ext = clean(stem) or "_", clean(ext)[:3]
    for n in range(1, 1000000):
        tail = "~%d" % n
        short = (stem[: 8 - len(tail)] + tail).ljust(8) + ext.ljust(3)
        if short not in taken:
            return short
    raise SystemExit("cannot generate a short name for " + name)


def fat_checksum(short):
    """Checksum of the 11-byte short name, stored in every LFN entry."""
    s = 0
    for c in short.encode("ascii"):
        s = (((s & 1) << 7) + (s >> 1) + c) & 0xFF
    return s


def fat_lfn_entries(name, short):
    """Long-file-name entries (13 UTF-16 chars each), highest sequence number first."""
    raw = name.encode("utf-16-le")
    u = list(struct.unpack("<%dH" % (len(raw) // 2), raw))
    if len(u) % 13:
        u.append(0)  # terminator
        u += [0xFFFF] * (-len(u) % 13)  # padding
    n = len(u) // 13
    csum = fat_checksum(short)
    out = []
    for i in range(n, 0, -1):
        c = u[(i - 1) * 13 : i * 13]
        out.append(
            struct.pack(
                "<B5HBBB6HH2H",
                i | (0x40 if i == n else 0),
                *c[:5],
                0x0F,
                0,
                csum,
                *c[5:11],
                0,
                *c[11:],
            )
        )
    return out


def fat_dirent(short, attr, cluster, size, ts):
    """A 32-byte short directory entry."""
    date, tm = fat_stamp(ts)
    return struct.pack(
        "<11sBBBHHHHHHHI",
        short.encode("ascii"),
        attr,
        0,
        0,
        tm,
        date,
        date,
        cluster >> 16,
        tm,
        date,
        cluster & 0xFFFF,
        size,
    )


class Fat32Filler:
    """Copies a host directory tree into the data region, allocating clusters
    sequentially. Every file/directory therefore gets one contiguous run."""

    EOC = 0x0FFFFFFF

    def __init__(self, f, bps, spc, data_start, clusters):
        self.f, self.bps, self.spc = f, bps, spc
        self.data_start, self.clusters = data_start, clusters
        self.csize = bps * spc
        self.fat = [0x0FFFFFF8, 0x0FFFFFFF, self.EOC]  # entries 0, 1 and the root (2)
        self.nfiles = self.ndirs = 0

    def alloc(self, n):
        first = len(self.fat)
        if first - 2 + n > self.clusters:
            raise SystemExit("staging directory does not fit in the image")
        self.fat.extend(range(first + 1, first + n))  # chain: c -> c+1 ...
        self.fat.append(self.EOC)  # ... last -> end of chain
        return list(range(first, first + n))

    def offset(self, cluster):
        return (self.data_start + (cluster - 2) * self.spc) * self.bps

    def scan(self, path):
        """List a host directory -> (children, number of 32-byte slots they need)."""
        kids, taken = [], set()
        for e in sorted(os.scandir(path), key=lambda e: e.name):
            if e.is_symlink() or not (e.is_dir() or e.is_file()):
                print("skipping (not representable on FAT):", e.path)
                continue
            if any(c in BAD_NAME_CHARS or ord(c) < 32 for c in e.name):
                raise SystemExit("illegal character in file name: %r" % e.name)
            units = len(e.name.encode("utf-16-le")) // 2
            if units > 255:
                raise SystemExit("file name too long: " + e.name)
            st = e.stat()
            kids.append(
                dict(
                    name=e.name,
                    path=e.path,
                    isdir=e.is_dir(),
                    size=st.st_size,
                    mtime=st.st_mtime,
                    units=units,
                    lfn=False,
                )
            )
        for k in kids:  # names that are already 8.3
            if fat_is_short(k["name"]):
                base, _, ext = k["name"].partition(".")
                k["short"] = base.ljust(8) + ext.ljust(3)
                taken.add(k["short"])
        slots = 0
        for k in kids:  # everything else: LFN + alias
            if "short" not in k:
                k["short"] = fat_alias(k["name"], taken)
                taken.add(k["short"])
                k["lfn"] = True
            slots += 1 + (-(-k["units"] // 13) if k["lfn"] else 0)
        return kids, slots

    def emit(self, chain, header, kids):
        """Write one directory (already allocated as `chain`) and everything below it."""
        entries = list(header)
        for k in kids:
            if k["isdir"]:
                sub, slots = self.scan(k["path"])
                sub_chain = self.alloc(max(1, -(-(slots + 2) * 32 // self.csize)))
                first = sub_chain[0]
                hdr = [
                    fat_dirent(".".ljust(11), 0x10, first, 0, k["mtime"]),
                    # '..' must be 0 when the parent is the root directory
                    fat_dirent(
                        "..".ljust(11), 0x10, 0 if chain[0] == 2 else chain[0], 0, k["mtime"]
                    ),
                ]
                self.emit(sub_chain, hdr, sub)
                cluster, attr, size = first, 0x10, 0
                self.ndirs += 1
            else:
                if k["size"] >= 1 << 32:
                    raise SystemExit("file too large for FAT32: " + k["name"])
                n = -(-k["size"] // self.csize)
                cluster = 0  # empty files own no cluster
                if n:
                    cluster = self.alloc(n)[0]
                    self.f.seek(self.offset(cluster))
                    with open(k["path"], "rb") as src:
                        shutil.copyfileobj(src, self.f)
                attr, size = 0x20, k["size"]  # 0x20 = archive
                self.nfiles += 1
            if k["lfn"]:
                entries += fat_lfn_entries(k["name"], k["short"])
            entries.append(fat_dirent(k["short"], attr, cluster, size, k["mtime"]))
        self.f.seek(self.offset(chain[0]))
        self.f.write(b"".join(entries))  # rest of the cluster stays zero

    def fat_bytes(self):
        return struct.pack("<%dI" % len(self.fat), *self.fat)


def make_fat32(path, size, label="NO NAME", staging=None):
    BPS = 512  # bytes per sector
    total = size // BPS  # total sectors

    # Cluster size: small images need small clusters, otherwise we end up
    # with < 65525 clusters and the volume would be detected as FAT16.
    if size <= 260 * MiB:
        spc = 1
    elif size <= 8 * GiB:
        spc = 8
    elif size <= 16 * GiB:
        spc = 16
    elif size <= 32 * GiB:
        spc = 32
    else:
        spc = 64

    reserved, nfats = 32, 2
    # Microsoft's formula for the FAT size (in sectors)
    t2 = (256 * spc + nfats) // 2
    fat_sectors = (total - reserved + t2 - 1) // t2
    data_start = reserved + nfats * fat_sectors  # first sector of cluster 2
    clusters = (total - data_start) // spc
    if clusters < 65525:
        raise SystemExit("Image too small for FAT32 (needs roughly >= 33 MiB)")

    label_b = label.upper().encode("ascii")[:11].ljust(11)

    # ---- Boot sector (BPB) ----
    boot = bytearray(BPS)
    boot[0:3] = b"\xeb\x58\x90"  # jmp short; nop
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into(
        "<HBHBHHBHHHII",
        boot,
        11,
        BPS,
        spc,
        reserved,
        nfats,
        0,  # root entries (0 on FAT32)
        0,  # total sectors 16-bit (0: use 32-bit)
        0xF8,  # media descriptor: fixed disk
        0,  # FAT size 16-bit (0 on FAT32)
        63,
        255,  # CHS geometry (ignored nowadays)
        0,  # hidden sectors
        total,
    )
    struct.pack_into(
        "<IHHIHH12x",
        boot,
        36,
        fat_sectors,  # FAT size 32-bit
        0,
        0,  # ext flags, fs version
        2,  # root directory cluster
        1,  # FSInfo sector
        6,
    )  # backup boot sector
    struct.pack_into(
        "<BBBI11s8s", boot, 64, 0x80, 0, 0x29, random.getrandbits(32), label_b, b"FAT32   "
    )
    boot[90:92] = b"\xeb\xfe"  # "boot code": jmp $ (hang)
    boot[510:512] = b"\x55\xaa"

    # ---- Sector 2: only carries the trailing signature ----
    sect2 = bytearray(BPS)
    sect2[510:512] = b"\x55\xaa"

    with open(path, "wb") as f:
        f.truncate(total * BPS)  # sparse, reads as zeros

        def put(sector, data):
            f.seek(sector * BPS)
            f.write(data)

        # ---- Populate: root directory first, then everything below it ----
        fill = Fat32Filler(f, BPS, spc, data_start, clusters)
        kids, slots = fill.scan(staging) if staging else ([], 0)
        root_chain = [2]
        extra = -(-(slots + 1) * 32 // (BPS * spc)) - 1  # +1 slot: volume label
        if extra > 0:  # big root: chain 2 -> 3 -> ...
            rest = fill.alloc(extra)
            fill.fat[2] = rest[0]
            root_chain += rest
        fill.emit(root_chain, [label_b + bytes([0x08]) + bytes(20)], kids)

        # ---- FSInfo sector (needs the final free-cluster count) ----
        used = len(fill.fat) - 2
        fsinfo = bytearray(BPS)
        struct.pack_into("<I", fsinfo, 0, 0x41615252)
        struct.pack_into("<I", fsinfo, 484, 0x61417272)
        struct.pack_into(
            "<II", fsinfo, 488, clusters - used, len(fill.fat) if used < clusters else 0xFFFFFFFF
        )
        struct.pack_into("<I", fsinfo, 508, 0xAA550000)

        for base in (0, 6):  # primary + backup copies
            put(base, boot)
            put(base + 1, fsinfo)
            put(base + 2, sect2)
        fat = fill.fat_bytes()
        for i in range(nfats):
            put(reserved + i * fat_sectors, fat)

    print(
        f"FAT32: {total} sectors, {spc * BPS} B/cluster, {clusters} clusters, "
        f"FAT = {fat_sectors} sectors x {nfats}; "
        f"{fill.nfiles} files, {fill.ndirs} dirs, {clusters - used} clusters free"
    )


# ───────────────────────────── ext2 ──────────────────────────────


def has_super(g):
    """With sparse_super, backups live only in groups 0, 1 and powers of 3, 5, 7."""
    if g <= 1:
        return True
    for base in (3, 5, 7):
        n = base
        while n < g:
            n *= base
        if n == g:
            return True
    return False


def set_bits(b, lo, hi):
    for i in range(lo, hi):
        b[i >> 3] |= 1 << (i & 7)


def pad_bits(b, valid):
    """Mark every bit from `valid` to the end of the bitmap block as in-use."""
    first = (valid + 7) // 8
    set_bits(b, valid, first * 8)
    b[first:] = b"\xff" * (len(b) - first)


def ptr60(ptrs):
    """i_block: 15 little-endian block pointers (12 direct + 3 indirect)."""
    return struct.pack("<15I", *(list(ptrs) + [0] * 15)[:15])


def inode_bytes(mode, links, size, nblocks, iblock, now, bs, mtime=None):
    raw = struct.pack(
        "<HHIIIIIHHIII60s",
        mode,
        0,
        size,
        now,
        now,
        int(mtime or now),
        0,  # mode uid size a/c/m/dtime
        0,
        links,
        nblocks * (bs // 512),  # gid links 512-byte blocks
        0,
        0,
        iblock,
    )  # flags osd1 i_block
    return raw + bytes(128 - len(raw))


def pack_dir(bs, entries):
    """entries = [(inode, name, file_type)] -> list of directory blocks.
    Entries never straddle a block; the last one in each block stretches to its end."""
    blocks, cur, used = [], [], 0
    for ino, name, ftype in entries:
        nb = name.encode()
        if len(nb) > 255:
            raise SystemExit("file name too long: " + name)
        rec = (8 + len(nb) + 3) & ~3
        if used + rec > bs:
            blocks.append(cur)
            cur, used = [], 0
        cur.append((ino, nb, ftype, rec))
        used += rec
    blocks.append(cur)
    out = []
    for cur in blocks:
        buf = bytearray()
        for i, (ino, nb, ftype, rec) in enumerate(cur):
            if i == len(cur) - 1:
                rec = bs - len(buf)
            buf += struct.pack("<IHBB", ino, rec, len(nb), ftype) + nb + bytes(rec - 8 - len(nb))
        out.append(bytes(buf))
    return out


def make_ext2(path, size, label="", block_size=None, staging=None):
    bs = block_size or (1024 if size < 512 * MiB else 4096)
    if bs not in (1024, 2048, 4096):
        raise SystemExit("block size must be 1024, 2048 or 4096")
    first_data = 1 if bs == 1024 else 0  # block 0 is the boot block on 1K fs
    bpg = bs * 8  # blocks per group (1 bitmap block)
    isz = 128  # inode size
    ipb = bs // isz  # inodes per block
    ppb = bs // 4  # block pointers per indirect block
    blocks = size // bs

    # ---- geometry (drop a last group that is too small to be useful) ----
    while True:
        ngroups = -(-(blocks - first_data) // bpg)
        ipg = -(-max(blocks * bs // 16384, 32) // ngroups)  # ~1 inode per 16 KiB
        ipg = min(-(-ipg // ipb) * ipb, bpg)  # fill whole blocks
        itb = ipg * isz // bs  # inode table blocks
        gdt = -(-ngroups * 32 // bs)  # descriptor blocks
        last = blocks - first_data - (ngroups - 1) * bpg
        need = (1 + gdt if has_super(ngroups - 1) else 0) + 2 + itb
        if ngroups > 1 and last < need + 50:
            blocks -= last
            continue
        break

    # ---- per-group layout: [sb + GDT] [block bmp] [inode bmp] [inode table] [data...] ----
    groups = []
    for g in range(ngroups):
        start = first_data + g * bpg
        n = min(bpg, blocks - start)
        base = start + (1 + gdt if has_super(g) else 0)
        groups.append(
            dict(
                start=start,
                n=n,
                bb=base,
                ib=base + 1,
                it=base + 2,
                nxt=base + 2 + itb - start,  # first free block (as group index)
                used_inodes=11 if g == 0 else 0,  # inodes 1..11 are taken
                dirs=2 if g == 0 else 0,
            )
        )  # root + lost+found

    now = int(time.time())
    with open(path, "wb") as f:
        f.truncate(blocks * bs)

        def put(block, data, offset=0):
            f.seek(block * bs + offset)
            f.write(data)

        # ---- allocators: space is only ever handed out, so each group's used
        #      region is always a prefix and a single counter per group is enough ----
        cur = [0]

        def alloc_block():
            while cur[0] < ngroups:
                gr = groups[cur[0]]
                if gr["nxt"] < gr["n"]:
                    gr["nxt"] += 1
                    return gr["start"] + gr["nxt"] - 1
                cur[0] += 1
            raise SystemExit("no space left in the image")

        next_ino = [12]

        def alloc_inode(is_dir):
            ino = next_ino[0]
            if ino > ipg * ngroups:
                raise SystemExit("out of inodes - use a larger image")
            next_ino[0] += 1
            gr = groups[(ino - 1) // ipg]
            gr["used_inodes"] += 1
            if is_dir:
                gr["dirs"] += 1
            return ino

        def put_inode(ino, raw):
            gr = groups[(ino - 1) // ipg]
            put(gr["it"], raw, ((ino - 1) % ipg) * isz)

        def build_ptrs(data):
            """Data block list -> (i_block bytes, [(block, content)] indirect blocks)."""
            meta = []

            def tree(blks, level):
                nb = alloc_block()
                if level == 1:
                    ptrs = blks
                else:
                    span = ppb ** (level - 1)
                    ptrs = [tree(blks[i : i + span], level - 1) for i in range(0, len(blks), span)]
                meta.append((nb, struct.pack("<%dI" % len(ptrs), *ptrs)))
                return nb

            ptrs, rest = list(data[:12]), list(data[12:])
            for level in (1, 2, 3):  # single, double, triple indirect
                if not rest:
                    break
                cap = ppb**level
                ptrs.append(tree(rest[:cap], level))
                rest = rest[cap:]
            if rest:
                raise SystemExit("file too large")
            return ptr60(ptrs), meta

        def add_file(ino, src_path, perm, st):
            if st.st_size >= 1 << 31:
                raise SystemExit("file too large for ext2 (>= 2 GiB): " + src_path)
            nd = -(-st.st_size // bs)
            data = [alloc_block() for _ in range(nd)]
            with open(src_path, "rb") as src:  # copy in runs of adjacent blocks
                i = 0
                while i < nd:
                    j = i + 1
                    while j < nd and j - i < 1024 and data[j] == data[j - 1] + 1:
                        j += 1
                    f.seek(data[i] * bs)
                    f.write(src.read((j - i) * bs))
                    i = j
            iblock, meta = build_ptrs(data)
            for b, raw in meta:
                put(b, raw)
            put_inode(
                ino,
                inode_bytes(
                    0o100000 | perm, 1, st.st_size, nd + len(meta), iblock, now, bs, st.st_mtime
                ),
            )

        def populate(path, ino, parent, mode, mtime, extra=()):
            """Write directory `ino` (copying host dir `path` into it, recursively)."""
            entries = [(ino, ".", 2), (parent, "..", 2)] + list(extra)
            links = 2 + len(extra)
            listing = sorted(os.scandir(path), key=lambda e: e.name) if path else []
            for e in listing:
                if ino == 2 and e.name == "lost+found":
                    continue
                st = e.stat(follow_symlinks=False)
                perm = st.st_mode & 0o7777
                if e.is_symlink():
                    target = os.readlink(e.path).encode()
                    child = alloc_inode(False)
                    if len(target) < 60:  # "fast" symlink: stored in i_block
                        raw = inode_bytes(
                            0o120777,
                            1,
                            len(target),
                            0,
                            target.ljust(60, b"\0"),
                            now,
                            bs,
                            st.st_mtime,
                        )
                    else:
                        if len(target) > bs:
                            raise SystemExit("symlink target too long: " + e.path)
                        blk = alloc_block()
                        put(blk, target)
                        raw = inode_bytes(
                            0o120777, 1, len(target), 1, ptr60([blk]), now, bs, st.st_mtime
                        )
                    put_inode(child, raw)
                    entries.append((child, e.name, 7))
                elif e.is_dir(follow_symlinks=False):
                    child = alloc_inode(True)
                    populate(e.path, child, ino, 0o40000 | perm, st.st_mtime)
                    links += 1  # the child's '..' points here
                    entries.append((child, e.name, 2))
                elif e.is_file(follow_symlinks=False):
                    child = alloc_inode(False)
                    add_file(child, e.path, perm, st)
                    entries.append((child, e.name, 1))
                else:
                    print("skipping special file:", e.path)
            blks = pack_dir(bs, entries)
            blist = [alloc_block() for _ in blks]
            for b, raw in zip(blist, blks):
                put(b, raw)
            iblock, meta = build_ptrs(blist)
            for b, raw in meta:
                put(b, raw)
            put_inode(
                ino,
                inode_bytes(
                    mode, links, len(blks) * bs, len(blks) + len(meta), iblock, now, bs, mtime
                ),
            )

        # ---- lost+found (inode 11): preallocated empty directory blocks ----
        lf_n = min(12, 16384 // bs)  # keep it within direct pointers
        lf_blks = [alloc_block() for _ in range(lf_n)]
        put(lf_blks[0], pack_dir(bs, [(11, ".", 2), (2, "..", 2)])[0])
        for b in lf_blks[1:]:
            put(b, pack_dir(bs, [(0, "", 0)])[0])  # empty slot
        put_inode(11, inode_bytes(0o40700, 2, lf_n * bs, lf_n, ptr60(lf_blks), now, bs))

        # ---- root directory (inode 2) and the staged tree ----
        if staging:
            st = os.stat(staging)
            populate(
                staging,
                2,
                2,
                0o40000 | (st.st_mode & 0o7777),
                st.st_mtime,
                extra=[(11, "lost+found", 2)],
            )
        else:
            populate(None, 2, 2, 0o40755, now, extra=[(11, "lost+found", 2)])

        # ---- bitmaps and counters, now that allocation is final ----
        for g, gr in enumerate(groups):
            bmap = bytearray(bs)
            set_bits(bmap, 0, gr["nxt"])
            pad_bits(bmap, gr["n"])
            imap = bytearray(bs)
            set_bits(imap, 0, gr["used_inodes"])
            pad_bits(imap, ipg)
            gr.update(
                bmap=bmap,
                imap=imap,
                free_blocks=gr["n"] - gr["nxt"],
                free_inodes=ipg - gr["used_inodes"],
            )

        free_blocks = sum(gr["free_blocks"] for gr in groups)
        free_inodes = sum(gr["free_inodes"] for gr in groups)
        log_bs = bs.bit_length() - 11  # 1024 -> 0, 2048 -> 1, 4096 -> 2
        fs_uuid = uuid.uuid4().bytes
        label_b = label.encode()[:16].ljust(16, b"\0")

        def superblock(g):
            sb = bytearray(1024)
            struct.pack_into(
                "<11I",
                sb,
                0,
                ipg * ngroups,
                blocks,
                blocks * 5 // 100,
                free_blocks,
                free_inodes,
                first_data,
                log_bs,
                log_bs,
                bpg,
                bpg,
                ipg,
            )
            struct.pack_into("<IIHhHHHH", sb, 44, 0, now, 0, -1, 0xEF53, 1, 1, 0)
            struct.pack_into(
                "<IIIIHHIHHIII",
                sb,
                64,
                now,
                0,
                0,
                1,  # lastcheck, interval, os=Linux, rev 1
                0,
                0,
                11,
                isz,
                g,  # resuid/gid, first_ino, inode size, group
                0,
                0x2,
                0x1,
            )  # compat, incompat=FILETYPE, ro=SPARSE_SUPER
            sb[104:120] = fs_uuid
            sb[120:136] = label_b
            return bytes(sb)

        gdt_raw = b"".join(
            struct.pack(
                "<IIIHHHH12x",
                gr["bb"],
                gr["ib"],
                gr["it"],
                gr["free_blocks"],
                gr["free_inodes"],
                gr["dirs"],
                0,
            )
            for gr in groups
        ).ljust(gdt * bs, b"\0")

        for g, gr in enumerate(groups):
            if has_super(g):
                if g == 0:
                    put(0, superblock(0), 1024)  # always at byte 1024
                else:
                    put(gr["start"], superblock(g))  # backups at the group start
                put(gr["start"] + 1, gdt_raw)
            put(gr["bb"], gr["bmap"])
            put(gr["ib"], gr["imap"])

    print(
        f"ext2: {blocks} blocks of {bs} B, {ngroups} groups, {ipg * ngroups} inodes; "
        f"{next_ino[0] - 12} staged entries, {free_blocks} blocks free"
    )


# ───────────────────────────── CLI ───────────────────────────────


def main():
    ap = argparse.ArgumentParser(description="Create FAT32 / ext2 images in pure Python")
    ap.add_argument("fs", choices=["fat32", "ext2"])
    ap.add_argument("image")
    ap.add_argument("size", help="e.g. 64M, 1G, 512K")
    ap.add_argument("--label", default=None)
    ap.add_argument("--block-size", type=int, default=None, help="ext2 only")
    ap.add_argument(
        "--populate",
        metavar="DIR",
        default=None,
        help="copy the contents of this staging directory into the image",
    )
    a = ap.parse_args()
    if a.populate and not os.path.isdir(a.populate):
        raise SystemExit("not a directory: " + a.populate)
    size = parse_size(a.size)
    if a.fs == "fat32":
        make_fat32(a.image, size, a.label or "NO NAME", a.populate)
    else:
        make_ext2(a.image, size, a.label or "", a.block_size, a.populate)


if __name__ == "__main__":
    main()
