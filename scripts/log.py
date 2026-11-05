def prRed(s):
    print("\033[91;1m{}\033[00m".format(s))


def prGreen(s):
    print("\033[32;1m{}\033[00m".format(s))


def prYellow(s):
    print("\033[93;1m{}\033[00m".format(s))


def prLightPurple(s):
    print("\033[94m{}\033[00m".format(s))


def prPurple(s):
    print("\033[95;1m{}\033[00m".format(s))


def prCyan(s):
    print("\033[96m{}\033[00m".format(s))


def prLightGray(s):
    print("\033[97;1m{}\033[00m".format(s))


def LOGE(s):
    prRed("[E]: {}".format(s))


def LOGI(s):
    prGreen("[I]: {}".format(s))


def LOGW(s):
    prYellow("[W]: {}".format(s))


def LOGD(s):
    prLightPurple("[D]: {}".format(s))
