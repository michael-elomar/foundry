import struct
from utils import SECTOR_SIZE, size_to_sectors

DEADBEEF = 3735928559
START_SECTOR = 2048

CHS_SEPARATOR = b"\xfe\xff\xff"

FORMATS = {
    "fat32": 0x0C,
    "ext2": 0x83,
}


class MBREntry:
    def __init__(self, start_lba, sectors, ptype, bootable=False) -> None:
        self.start_lba = start_lba
        self.sectors = sectors
        self.partition_type = ptype
        self.bootable = bootable

    def toBytes(self) -> bytes:
        return struct.pack(
            "<B3sB3sII",
            0x80 if self.bootable else 0x00,
            CHS_SEPARATOR,
            self.partition_type,
            CHS_SEPARATOR,
            self.start_lba,
            self.sectors,
        )

    @classmethod
    def createEntry(cls, format: str, sectors: int, start: int, bootable: bool = False):
        return MBREntry(start, sectors, FORMATS[format], bootable)


class MBRDiskImage:
    def __init__(self, format_size_dict: dict[str, str], disk_id: int = 0) -> None:
        self.format_size_dict = format_size_dict
        self.disk_id = disk_id
        self.start = 2048  # MBR constant
        self.mbr_entries: list[MBREntry] = []
        self.total_size = 1  # in sectors
        self.buildMBR()

    def buildMBR(self) -> list[MBREntry]:
        start = self.start
        for i, (format, size) in enumerate(self.format_size_dict.items()):
            sectors = size_to_sectors(size)
            self.total_size += sectors
            self.mbr_entries.append(MBREntry.createEntry(format, sectors, start, i == 0))
            start += size_to_sectors(size)
        return self.mbr_entries

    def toBytes(self) -> bytes:
        mbr_array = bytearray(SECTOR_SIZE)
        mbr_array[440:446] = struct.pack("<I", self.disk_id)
        for i, entry in enumerate(self.mbr_entries):
            # fill the current 16 bytes reserved for
            # the partition represented by the current mbr entry
            mbr_array[446 + 16 * i : 462 + 16 * i] = entry.toBytes()

        # MBR final signature
        mbr_array[510:512] = b"\x55\xaa"
        return bytes(mbr_array)
