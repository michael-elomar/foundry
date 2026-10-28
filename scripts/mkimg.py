#! /usr/bin/env python3

import mbr
import sys
import argparse

from utils import SECTOR_SIZE, size_to_sectors
import fat32
import extfs
import offset_file


class AtLeastThree(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if not len(values) % 3 == 0:
            msg = 'argument "{f}" requires at least arguments: FORMAT SIZE DIR'.format(f=self.dest)
            raise argparse.ArgumentTypeError(msg)
        setattr(args, self.dest, values)


def parse_args(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--partitions",
        dest="partitions",
        nargs="+",
        help="provide partitioning info in the following"
        " order: format1 size1 dir1 [format2 size2 dir2 ...]",
        action=AtLeastThree,
        required=True,
    )

    parser.add_argument(
        "--output",
        dest="output",
        help="Path to the generated disk image",
        required=True,
    )

    return vars(parser.parse_args(argv))


def main(argv=None):
    if not argv:
        argv = sys.argv[1:]

    options = parse_args(argv)

    formats = [options["partitions"][i] for i in range(0, len(options["partitions"]), 3)]
    sizes = [options["partitions"][i] for i in range(1, len(options["partitions"]), 3)]
    dirs = [options["partitions"][i] for i in range(2, len(options["partitions"]), 3)]

    fmt_size = {}
    for i, fmt in enumerate(formats):
        fmt_size[fmt] = sizes[i]

    disk_image = mbr.MBRDiskImage(fmt_size, mbr.DEADBEEF)

    with open(options["output"], "wb+") as file:
        file.truncate(disk_image.total_size * SECTOR_SIZE)
        file.write(disk_image.toBytes())

        BOOT_PARITION_SIZE = size_to_sectors(sizes[0])

        boot_partition = offset_file.OffsetFile(
            file, mbr.START_SECTOR * SECTOR_SIZE, BOOT_PARITION_SIZE * SECTOR_SIZE
        )
        fat32_fs = fat32.Fat32(boot_partition, mbr.START_SECTOR)
        fat32_fs.format(label="Boot")
        fat32_fs.add_tree(dirs[0])
        fat32_fs.close()

        ROOT_PARTITION_OFFSET = BOOT_PARITION_SIZE + mbr.START_SECTOR
        ROOT_PARTITION_SIZE = size_to_sectors(sizes[1]) - mbr.START_SECTOR

        roots_partition = offset_file.OffsetFile(
            file, ROOT_PARTITION_OFFSET * SECTOR_SIZE, ROOT_PARTITION_SIZE * SECTOR_SIZE
        )
        ext2_fs = extfs.Ext2(roots_partition)
        ext2_fs.format(label="Linux")
        ext2_fs.add_tree(dirs[1])  # tree structure preserved
        ext2_fs.close()


if __name__ == "__main__":
    main()
