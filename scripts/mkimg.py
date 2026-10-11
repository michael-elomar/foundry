#! /usr/bin/env python3
"""
mkimg.py - build FAT32 and ext2 filesystem images from scratch, pure Python.

    python3 mkimg.py fat32 disk.img 64M --label MYDISK
    python3 mkimg.py ext2  disk.img 64M --label data [--block-size 4096]

Images are sparse files: only the metadata is actually written to disk.
"""

import argparse
import random
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


def make_fat32(path, size, label="NO NAME"):
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

    # ---- FSInfo sector ----
    fsinfo = bytearray(BPS)
    struct.pack_into("<I", fsinfo, 0, 0x41615252)
    struct.pack_into("<I", fsinfo, 484, 0x61417272)
    struct.pack_into("<II", fsinfo, 488, clusters - 1, 3)  # free count, next free
    struct.pack_into("<I", fsinfo, 508, 0xAA550000)

    # ---- Sector 2: only carries the trailing signature ----
    sect2 = bytearray(BPS)
    sect2[510:512] = b"\x55\xaa"

    # ---- First FAT sector: media entry, reserved entry, root dir (EOC) ----
    fat_head = struct.pack("<III", 0x0FFFFFF8, 0x0FFFFFFF, 0x0FFFFFFF)

    # ---- Root directory (cluster 2) holds just the volume label ----
    root_entry = label_b + bytes([0x08]) + bytes(20)

    with open(path, "wb") as f:
        f.truncate(total * BPS)  # sparse, reads as zeros

        def put(sector, data):
            f.seek(sector * BPS)
            f.write(data)

        for base in (0, 6):  # primary + backup copies
            put(base, boot)
            put(base + 1, fsinfo)
            put(base + 2, sect2)
        for i in range(nfats):
            put(reserved + i * fat_sectors, fat_head)
        put(data_start, root_entry)

    print(
        f"FAT32: {total} sectors, {spc * BPS} B/cluster, "
        f"{clusters} clusters, FAT = {fat_sectors} sectors x {nfats}"
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


def inode_bytes(mode, links, size, nblocks, block_list, now, bs):
    ptrs = (block_list + [0] * 15)[:15]
    raw = struct.pack(
        "<HHIIIIIHHIII15I",
        mode,
        0,
        size,
        now,
        now,
        now,
        0,  # mode uid size a/c/m/dtime
        0,
        links,
        nblocks * (bs // 512),  # gid links 512-byte blocks
        0,
        0,
        *ptrs,
    )  # flags osd1 i_block[15]
    return raw + bytes(128 - len(raw))


def dir_block(bs, entries):
    """entries = [(inode, name, file_type)]; the last one stretches to block end."""
    out = bytearray()
    for i, (ino, name, ftype) in enumerate(entries):
        nb = name.encode()
        rec = (8 + len(nb) + 3) & ~3
        if i == len(entries) - 1:
            rec = bs - len(out)
        out += struct.pack("<IHBB", ino, rec, len(nb), ftype) + nb + bytes(rec - 8 - len(nb))
    return bytes(out)


def make_ext2(path, size, label="", block_size=None):
    bs = block_size or (1024 if size < 512 * MiB else 4096)
    if bs not in (1024, 2048, 4096):
        raise SystemExit("block size must be 1024, 2048 or 4096")
    first_data = 1 if bs == 1024 else 0  # block 0 is the boot block on 1K fs
    bpg = bs * 8  # blocks per group (1 bitmap block)
    isz = 128  # inode size
    ipb = bs // isz  # inodes per block
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

    # ---- per-group layout: [sb + GDT] [block bmp] [inode bmp] [inode table] ----
    groups = []
    for g in range(ngroups):
        start = first_data + g * bpg
        n = min(bpg, blocks - start)
        base = start + (1 + gdt if has_super(g) else 0)
        groups.append(
            dict(start=start, n=n, bb=base, ib=base + 1, it=base + 2, free0=base + 2 + itb)
        )

    # ---- root dir (inode 2) and lost+found (inode 11) live in group 0 ----
    g0 = groups[0]
    lf_n = min(12, 16384 // bs)  # keep it within direct pointers
    root_blk = g0["free0"]
    lf_blks = list(range(root_blk + 1, root_blk + 1 + lf_n))
    if lf_blks[-1] >= g0["start"] + g0["n"]:
        raise SystemExit("Image too small for ext2")

    now = int(time.time())
    for g, gr in enumerate(groups):
        used = gr["free0"] - gr["start"] + ((1 + lf_n) if g == 0 else 0)
        bmap = bytearray(bs)
        set_bits(bmap, 0, used)
        pad_bits(bmap, gr["n"])
        imap = bytearray(bs)
        if g == 0:
            set_bits(imap, 0, 11)  # inodes 1..10 reserved + 11 l+f
        pad_bits(imap, ipg)
        gr.update(
            bmap=bmap,
            imap=imap,
            free_blocks=gr["n"] - used,
            free_inodes=ipg - (11 if g == 0 else 0),
            dirs=2 if g == 0 else 0,
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

    with open(path, "wb") as f:
        f.truncate(blocks * bs)

        def put(block, data, offset=0):
            f.seek(block * bs + offset)
            f.write(data)

        for g, gr in enumerate(groups):
            if has_super(g):
                if g == 0:
                    put(0, superblock(0), 1024)  # always at byte 1024
                else:
                    put(gr["start"], superblock(g))
                put(gr["start"] + 1, gdt_raw)
            put(gr["bb"], gr["bmap"])
            put(gr["ib"], gr["imap"])

        # inodes 2 (root) and 11 (lost+found)
        def put_inode(ino, data):
            put(g0["it"], data, (ino - 1) * isz)

        put_inode(2, inode_bytes(0o40755, 3, bs, 1, [root_blk], now, bs))
        put_inode(11, inode_bytes(0o40700, 2, lf_n * bs, lf_n, lf_blks, now, bs))

        # directory contents (file type 2 = directory)
        put(root_blk, dir_block(bs, [(2, ".", 2), (2, "..", 2), (11, "lost+found", 2)]))
        put(lf_blks[0], dir_block(bs, [(11, ".", 2), (2, "..", 2)]))
        for blk in lf_blks[1:]:
            put(blk, dir_block(bs, [(0, "", 0)]))  # empty slot

    print(
        f"ext2: {blocks} blocks of {bs} B, {ngroups} groups, "
        f"{ipg * ngroups} inodes, {free_blocks} blocks free"
    )


# ───────────────────────────── CLI ───────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Create FAT32 / ext2 images in pure Python")
    parser.add_argument("fs", choices=["fat32", "ext2"])
    parser.add_argument("image")
    parser.add_argument("size", help="e.g. 64M, 1G, 512K")
    parser.add_argument("--label", default=None)
    parser.add_argument("--block-size", type=int, default=None, help="ext2 only")
    options = parser.parse_args()
    size = parse_size(options.size)
    if options.fs == "fat32":
        make_fat32(options.image, size, options.label or "NO NAME")
    else:
        make_ext2(options.image, size, options.label or "", options.block_size)


if __name__ == "__main__":
    main()
