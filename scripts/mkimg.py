#! /usr/bin/env python3
"""
mkimg.py - build FAT32 and ext2 filesystem images from scratch, pure Python.

    python3 mkimg.py fat32 disk.img 64M --label MYDISK
    python3 mkimg.py ext2  disk.img 64M --label data [--block-size 4096]

Images are sparse files: only the metadata is actually written to disk.
"""

import argparse


def create_empty_image(image_path):
    print(image_path)


def main():
    parser = argparse.ArgumentParser(description="Create FAT32 / ext2 images in pure Python")

    parser.add_argument(
        "--partitions",
        required=True,
        nargs="+",
        help="string of partitions",
    )
    parser.add_argument(
        "--output",
        required=True,
    )

    options = parser.parse_args()

    create_empty_image(options.output)


if __name__ == "__main__":
    main()
