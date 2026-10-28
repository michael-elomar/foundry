import struct

SECTOR = 512
DEADBEEF = 3735928559
START_SECTOR = 2048


class OffsetFile:
    """File-like view of a region of another file: what a partition is."""

    def __init__(self, f, offset, size):
        self.f, self.offset, self.size, self.pos = f, offset, size, 0

    def seek(self, pos, whence=0):
        if whence == 0:
            self.pos = pos
        elif whence == 1:
            self.pos += pos
        else:
            self.pos = self.size + pos
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        self.f.seek(self.offset + self.pos)
        data = self.f.read(n)
        self.pos += len(data)
        return data

    def write(self, data):
        if self.pos + len(data) > self.size:
            raise ValueError("write past partition end")
        self.f.seek(self.offset + self.pos)
        self.f.write(data)
        self.pos += len(data)
        return len(data)


def mbr_entry(start_lba, sectors, ptype, bootable=False):
    return struct.pack(
        "<B3sB3sII",
        0x80 if bootable else 0,
        b"\xfe\xff\xff",
        ptype,
        b"\xfe\xff\xff",
        start_lba,
        sectors,
    )


def build_mbr(entries):
    mbr = bytearray(512)
    mbr[440:446] = struct.pack("<I", DEADBEEF)
    for i, e in enumerate(entries):
        mbr[446 + 16 * i : 462 + 16 * i] = e
    mbr[510:512] = b"\x55\xaa"
    return bytes(mbr)


# with open("disk.img", "wb") as f:
#     f.truncate(2304000 * SECTOR)  # sparse file
#     f.write(
#         build_mbr(
#             [
#                 mbr_entry(2048, 204800, 0x0C, True),  # FAT32 LBA
#                 mbr_entry(206848, 2097152, 0x83),  # Linux
#             ]
#         )
#     )
#     fat_part = OffsetFile(f, 2048 * SECTOR, 204800 * SECTOR)
#     ext_part = OffsetFile(f, 206848 * SECTOR, 2097152 * SECTOR)
#     # pass fat_part / ext_part to your FAT32 / EXT2 formatters
