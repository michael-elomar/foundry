#! /usr/bin/env python3

import argparse
import os
import pathlib
import subprocess
import sys

from trace import *


def main(argv=None):
    cwd = pathlib.Path(os.getcwd())
    forge_mk = cwd / "forge.mk"
    if not os.path.isfile(forge_mk):
        LOGE(f"'forge.mk' file was not found at {cwd}")
        exit()

    if not argv:
        argv = sys.argv[2:]

    BUILD_SYSTEM = sys.argv[1]

    options = parse_args(argv)

    cmd = [
        "make",
        "-f",
        f"{BUILD_SYSTEM}/makefiles/main.mk",
        "-j",
        options["build_jobs"],
    ]

    if options["forge_target"]:
        cmd += [options["forge_target"]]

    env = os.environ
    env["CWD"] = str(cwd)
    env["FORGE_MK"] = str(forge_mk)
    env["BUILD_SYSTEM"] = str(BUILD_SYSTEM)

    subprocess.run(cmd, env=env)


def parse_args(argv):
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-F",
        default="all",
        dest="forge_target",
        help="Name of the target to be built as specified in a 'forge'.mk file",
    )

    parser.add_argument(
        "-j",
        default="1",
        dest="build_jobs",
        help="Number of build jobs to be executed",
    )

    return vars(parser.parse_args(argv))


if __name__ == "__main__":
    main()
