SECTOR = 512


def size_to_sectors(size: str):
    size = size.upper().strip()
    multipliers = {
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
    }

    suffix = ""
    mult = 0
    for k in multipliers.keys():
        if size.endswith(k):
            suffix = k
            mult = multipliers[k]
    if mult == 0:
        raise ValueError("{} is not a valid size format".format(size))

    # get value without suffix: 100M ==> 100
    size = size.strip(suffix)

    # convert value to bytes
    size_in_bytes = int(int(size) * mult)

    # divide by sector size to get number of sectors, no remainder
    return size_in_bytes // SECTOR
