#! /usr/bin/env python3
"""
Generate partitioned disk images.

Usage:
    python create_disk_image.py output.img NUM_PARTITIONS SIZE1 FORMAT1 SIZE2 FORMAT2 ...

Example:
    python create_disk_image.py disk.img 2 100M fat32 500M ext4
    Creates a disk image with 2 partitions: 100MB FAT32 and 500MB ext4
"""

import os
import argparse
import subprocess
import shlex
import shutil
from trace import LOGE

# Map filesystem names to mkfs commands
FS_TOOLS = {
    "fat16": ["mkfs.vfat", "-F", "16"],
    "fat32": ["mkfs.vfat", "-F", "32", "-n", "BOOT"],
    "vfat": ["mkfs.vfat", "-F", "32"],
    "ext2": ["mkfs.ext2", "-L", "linux"],
    "ext3": ["mkfs.ext3", "-L", "linux"],
    "ext4": ["mkfs.ext4", "-L", "linux"],
}


def create_disk_image(image_path, total_size):
    subprocess.run(["truncate", "-s", str(total_size * 1024 * 1024), image_path], check=True)


def parse_size(size_str):
    """Parse size string like '100M', '1G' to MB."""
    size_str = size_str.upper().strip()
    multipliers = {
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024 * 1024,
        "MB": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "T": 1024**4,
        "TB": 1024**4,
    }
    for suffix, mult in sorted(multipliers.items(), key=lambda x: -len(x[0])):
        if size_str.endswith(suffix):
            return int((float(size_str[: -len(suffix)]) * mult) / multipliers["M"])
    else:
        raise ValueError("Invalid suffix in partition sizes")


def partition_disk(image_path, partition_sizes, partition_formats, label="msdos"):
    """Create partitions using parted."""
    """parted --script out/avalon.img mklabel msdos mkpart primary fat32 1MiB 100MiB mkpart primary ext2 100MiB 100%"""
    command = [
        "parted",
        "--script",
        image_path,
        "mklabel",
        label,
    ]
    start = 1
    for i in range(len(partition_sizes) - 1):
        end = start + partition_sizes[i]
        partition_cmd = [
            "mkpart",
            "primary",
            partition_formats[i],
            "{}MiB".format(start),
            "{}MiB".format(end),
        ]
        command.extend(partition_cmd)
        start = end

    partition_cmd = [
        "mkpart",
        "primary",
        partition_formats[-1],
        "{}MiB".format(start),
        "100%",
    ]
    command.extend(partition_cmd)

    p = subprocess.run(command, check=True)
    if p.returncode != 0:
        LOGE(
            "Partition command field.\nret: {}\nstdout: {}\nstderrr: {}".format(
                p.returncode, p.stdout, p.stderr
            )
        )


def fill_partitions(image_path, dirs, formats):
    """
    # 1. Attach the image as a loop device with partition scanning
    LOOP=$(sudo losetup --find --show --partscan disk.img)

    # 2. Create mount points
    sudo mkdir -p /mnt/part1 /mnt/part2  # adjust based on number of partitions

    sudo mkfs.vfat -F 32 -n BOOT /dev/loop0p1
    sudo mkfs.ext2 -L linux      /dev/loop0p2

    # 3. Mount each partition
    sudo mount "${LOOP}p1" /mnt/part1
    sudo mount "${LOOP}p2" /mnt/part2

    # 4. Copy your files
    sudo cp -r /path/to/your/files/* /mnt/part1/
    sudo cp -r /path/to/more/files/* /mnt/part2/

    # 5. Unmount
    sudo umount /mnt/part1 /mnt/part2

    # 6. Detach loop device
    sudo losetup -d "$LOOP"
    """
    p = subprocess.run(
        shlex.split("sudo losetup --find --show --partscan {}".format(image_path)),
        capture_output=True,
    )
    loop_device = p.stdout.strip().decode()
    mounted = list()
    for i in range(len(dirs)):
        fs_cmd = ["sudo"]
        fs_cmd.extend(FS_TOOLS[formats[i]])
        fs_cmd.append("{}p{}".format(loop_device, i + 1))
        subprocess.run(fs_cmd)

        mount_dir = "/tmp/mnt/part{}".format(i + 1)
        os.makedirs(mount_dir, exist_ok=True)
        mount_cmd = ["sudo", "mount", "{}p{}".format(loop_device, i + 1), mount_dir]
        mounted.append(mount_dir)

        subprocess.run(mount_cmd)

        copy_cmd = [
            "sudo",
            "cp",
            "-r",
            "{}/*".format(dirs[i]),
            mount_dir,
        ]

        subprocess.run(copy_cmd, shell=True)

    __import__("pdb").set_trace()

    subprocess.run(["sudo", "umount"] + mounted)

    p = subprocess.run(
        shlex.split("sudo losetup -d {}".format(loop_device)),
        capture_output=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Generate partitioned disk images",
        epilog="Example: mkimg.py --partitions fat32 100M ext2 1G --output disk.img",
    )
    parser.add_argument("--output", help="Output image path", required=True)
    parser.add_argument(
        "--partitions",
        nargs="+",
        help="Partition sizes and formats (e.g., 100M fat32 DIR1 1G ext4 DIR2)",
    )

    args = parser.parse_args()

    formats = [args.partitions[i] for i in range(0, len(args.partitions), 3)]
    sizes = [args.partitions[i] for i in range(1, len(args.partitions), 3)]
    dirs = [args.partitions[i] for i in range(2, len(args.partitions), 3)]

    sizes = [parse_size(s) for s in sizes]
    total = sum(sizes)

    create_disk_image(args.output, total)

    partition_disk(args.output, sizes, formats)

    fill_partitions(args.output, dirs, formats)


if __name__ == "__main__":
    main()
