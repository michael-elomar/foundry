#! /usr/bin/env python3
"""
Generate partitioned disk images.

Usage:
    python create_disk_image.py output.img NUM_PARTITIONS SIZE1 FORMAT1 SIZE2 FORMAT2 ...

Example:
    python create_disk_image.py disk.img 2 100M fat32 500M ext4
    Creates a disk image with 2 partitions: 100MB FAT32 and 500MB ext4
"""

import argparse
import subprocess
import os
import time


def parse_size(size_str):
    """Parse size string like '100M', '1G' to bytes."""
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
            return int(float(size_str[: -len(suffix)]) * mult)
    return int(size_str)


def create_disk_image(output_path, total_size_bytes):
    """Create sparse disk image."""
    subprocess.run(["truncate", "-s", str(total_size_bytes), output_path], check=True)


def partition_disk(image_path, partition_sizes_bytes, label="msdos"):
    """Create partitions using parted."""
    start = 512
    for size in partition_sizes_bytes:
        commands = [f"mklabel {label}"]
        end = start + size
        commands.append(f"mkpart primary {start}B {end}B")
        commands = ["parted", "--script", image_path] + commands
        print(" ".join(commands))
        subprocess.run(commands, check=True)
        start = end


def setup_loop_device(image_path):
    """Attach image as loop device with partition scanning."""
    result = subprocess.run(
        ["losetup", "--find", "--show", "--partscan", image_path],
        capture_output=True,
        text=True,
        check=True,
    )
    time.sleep(2)  # Wait for partitions to appear
    return result.stdout.strip()


def get_partition_devices(loop_device):
    """Get partition devices from loop device."""
    base = os.path.basename(loop_device)
    devices = []
    for i in range(1, 10):
        for prefix in ["", "p"]:
            path = f"/dev/{prefix}{base}{i}" if prefix else f"/dev/{base}{i}"
            if os.path.exists(path):
                devices.append(path)
    return sorted(devices)


def format_partition(device, fs_type):
    """Format partition with specified filesystem."""
    fs_type = fs_type.lower()
    mkfs_cmds = {
        "fat16": ["mkfs.vfat", "-F", "16"],
        "fat32": ["mkfs.vfat", "-F", "32"],
        "ext2": ["mkfs.ext2", "-F"],
        "ext3": ["mkfs.ext3", "-F"],
        "ext4": ["mkfs.ext4", "-F"],
        "ntfs": ["mkfs.ntfs", "-f"],
    }
    if fs_type not in mkfs_cmds:
        raise ValueError(f"Unsupported filesystem: {fs_type}")
    subprocess.run(mkfs_cmds[fs_type] + [device], check=True)


def cleanup(loop_device):
    """Detach loop device."""
    base = os.path.basename(loop_device)
    for i in range(10, 0, -1):
        for prefix in ["p", ""]:
            path = f"/dev/{prefix}{base}{i}" if prefix else f"/dev/{base}{i}"
            subprocess.run(["losetup", "-d", path], check=False)
    subprocess.run(["losetup", "-d", loop_device], check=False)


def main():
    parser = argparse.ArgumentParser(
        description="Generate partitioned disk images",
        epilog="Example: create_disk_image.py img 2 100M fat32 500M ext4",
    )
    parser.add_argument("--output", help="Output image path", required=True)
    parser.add_argument(
        "--partitions",
        nargs="+",
        help="Partition sizes and formats (e.g., 100M fat32 1G ext4)",
    )

    args = parser.parse_args()

    sizes = [args.partitions[i] for i in range(0, len(args.partitions), 2)]
    formats = [args.partitions[i] for i in range(1, len(args.partitions), 2)]

    print(sizes, formats)

    sizes = [parse_size(s) for s in sizes]
    total = sum(sizes)

    print(f"Creating {total/(1024**3):.2f}GB image with {len(sizes)} partitions")
    create_disk_image(args.output, total)
    # partition_disk(args.output, sizes)
    #
    # loop = setup_loop_device(args.output)
    # try:
    #     partitions = get_partition_devices(loop)
    #     for i, (p, fmt) in enumerate(zip(partitions, formats), 1):
    #         print(f"Formatting partition {i} ({p}) as {fmt}...")
    #         format_partition(p, fmt)
    # finally:
    #     cleanup(loop)

    print(f"Done: {args.output}")


if __name__ == "__main__":
    main()
