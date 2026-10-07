$(call module-add)

BUSYBOX_BUILD_DIR := $(OBJ_DIR)/$(LOCAL_MODULE)

ifndef TARGET_BUSYBOX_ARCHIVE_LINK
TARGET_BUSYBOX_ARCHIVE_LINK := https://www.busybox.net/downloads/busybox-$(TARGET_BUSYBOX_VERSION).tar.bz2
endif

__download_busybox = \
	$(shell wget -nc -P $(BUILD_DIR) $(TARGET_BUSYBOX_ARCHIVE_LINK)) \
	$(shell tar -xf $(BUILD_DIR)/busybox-$(TARGET_BUSYBOX_VERSION).tar.bz2 -C $(BUILD_DIR))


BUSYBOX_MAKE_ARGS := \
	ARCH="$(LINUX_ARCH)" \
	CROSS_COMPILE=$(TARGET_CC) \
	-C $(BUILD_DIR)/busybox-$(TARGET_BUSYBOX_VERSION) \
	O="$(BUSYBOX_BUILD_DIR)" \
	CFLAGS="--sysroot=$(STAGING_DIR)" \
	CONFIG_PREFIX=$(STAGING_DIR) \
	$(TARGET_BUSYBOX_MAKE_BUILD_ARGS)

