#! /usr/bin/env python3

import argparse
import os
import pathlib
import subprocess
import sys

from trace import *


def check_product(product, products_path):
    return product in os.listdir(products_path)


def get_forge_mk_files(workspace):
    forge_mk_files = []
    # Traverse all directories and subdirectories
    for path in workspace.rglob("forge.mk"):
        forge_mk_files.append(str(path.resolve()))

    return forge_mk_files


def main(argv=None):
    cwd = pathlib.Path(os.getcwd())
    # forge_mk = cwd / "forge.mk"
    # if not os.path.isfile(forge_mk):
    #     LOGE(f"'forge.mk' file was not found at {cwd}")
    #     exit(-1)

    if not argv:
        argv = sys.argv[2:]

    BUILD_SYSTEM = pathlib.Path(sys.argv[1])
    WORKSPACE = BUILD_SYSTEM.parents[1]
    PRODUCTS = WORKSPACE / "products"

    options = parse_args(argv)

    if not check_product(options["product"], PRODUCTS):
        LOGE("Product '{}' is not defined in workspace".format(options["product"]))
        exit(-1)

    forge_mk_files = get_forge_mk_files(WORKSPACE)
    # Convert the list to a space-separated string
    files_str = " ".join(forge_mk_files)

    if options["dry_run"]:
        cmd = [
            "make",
            "-n",
            "-p",
            "-f",
            f"{BUILD_SYSTEM}/makefiles/main.mk",
            "-I",
            str(PRODUCTS / options["product"]),
        ]
    else:
        cmd = [
            "make",
            "-f",
            f"{BUILD_SYSTEM}/makefiles/main.mk",
            "-j",
            options["build_jobs"],
            "-I",
            str(PRODUCTS / options["product"]),
        ]

    cmd += [options["forge_target"]]

    env = os.environ
    env["CWD"] = str(cwd)
    env["FORGE_MK_FILES"] = files_str
    env["BUILD_SYSTEM"] = str(BUILD_SYSTEM)
    env["WORKSPACE"] = str(WORKSPACE)
    env["JOBS"] = options["build_jobs"]

    if options["dry_run"]:
        with open("Makefile.txt", "w") as file:
            subprocess.run(cmd, env=env, stdout=file, stderr=file)
    else:
        subprocess.run(cmd, env=env)


def parse_args(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-F",
        dest="forge_target",
        default="all",
        help="if specified, system will find and build only"
        "the specified target and its dependencies",
        required=False,
    )

    parser.add_argument(
        "-j",
        default="1",
        dest="build_jobs",
        help="Number of build jobs to be executed",
    )

    parser.add_argument(
        "-t",
        default="all",
        dest="task",
        help="Specify task to be executed by the build system",
    )

    parser.add_argument(
        "-p",
        dest="product",
        required=True,
        help="Specify product to be built",
    )

    parser.add_argument(
        "-n",
        "--dry-run",
        dest="dry_run",
        action="store_true",
    )

    return vars(parser.parse_args(argv))


if __name__ == "__main__":
    main()
