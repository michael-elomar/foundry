$(call module-add)

LINUX_BUILD_DIR := $(OBJ_DIR)/$(LOCAL_MODULE)

KERNEL_ARCHIVE_LINK := https://cdn.kernel.org/pub/linux/kernel/
KERNEL_SRC_FOLDER := linux-$(TARGET_OS_VERSION)

# LINUX_SRCARCH is the name of the sub-directory in linux/arch
ifeq ("$(TARGET_ARCH)","x64")
  LINUX_ARCH := x86_64
  LINUX_SRCARCH := x86
else ifeq ("$(TARGET_ARCH)","aarch64")
  LINUX_ARCH := arm64
  LINUX_SRCARCH := arm64
else
  LINUX_ARCH := $(TARGET_ARCH)
  LINUX_SRCARCH := $(TARGET_ARCH)
endif

# Linux image to generate
ifndef LINUX_IMAGE
  ifeq ("$(TARGET_LINUX_GENERATE_UIMAGE)","1")
    LINUX_IMAGE := uImage
  else ifeq ("$(TARGET_ARCH)","x86")
    LINUX_IMAGE := bzImage
  else ifeq ("$(TARGET_ARCH)","x64")
    LINUX_IMAGE := bzImage
  else ifeq ("$(TARGET_ARCH)","arm")
    LINUX_IMAGE := zImage
  else ifeq ("$(TARGET_ARCH)","aarch64")
    LINUX_IMAGE := Image
  else
    LINUX_IMAGE := zImage
  endif
endif

LINUX_MAKE_ARGS := \
	ARCH="$(LINUX_ARCH)" \
	CROSS_COMPILE=$(TARGET_LINUX_CROSS) \
	INSTALL_MOD_PATH=$(STAGING_DIR) \
	INSTALL_DTBS_PATH=$(STAGING_DIR)/boot \
	-C $(BUILD_DIR)/$(KERNEL_SRC_FOLDER) \
	O="$(LINUX_BUILD_DIR)" \
	$(TARGET_LINUX_MAKE_BUILD_ARGS) $(LOCAL_LINUX_MAKE_BUILD_ARGS) \
	DEPMOD="$(LINUX_DEPMOD)"

__download_kernel = \
	$(shell wget -nc -P $(BUILD_DIR) $(KERNEL_ARCHIVE_LINK)/v$(TARGET_OS_MAJOR_VERSION).x/$(KERNEL_SRC_FOLDER).tar.xz) \
	$(shell tar -xf $(BUILD_DIR)/$(KERNEL_SRC_FOLDER).tar.xz -C $(BUILD_DIR))

linux-copy-image = \
	$(if $(call streq,$(LINUX_IMAGE),$1), \
		if [ -f $(LINUX_BUILD_DIR)/arch/$(LINUX_SRCARCH)/boot/$1 ]; then \
			cp -af $(LINUX_BUILD_DIR)/arch/$(LINUX_SRCARCH)/boot/$1 $(STAGING_DIR)/boot; \
		fi; \
	)

define linux-copy-images
	$(Q) $(call linux-copy-image,uImage)
	$(Q) $(call linux-copy-image,Image)
	$(Q) $(call linux-copy-image,Image.gz)
	$(Q) $(call linux-copy-image,zImage)
	$(Q) $(call linux-copy-image,bzImage)
endef


LINUX_SDK_DIR := $(STAGING_DIR)/usr/src/linux-sdk
define linux-gen-sdk
	$(Q) :> $(LINUX_BUILD_DIR)/sdksrcfiles
	$(Q) :> $(LINUX_BUILD_DIR)/sdkobjfiles
	$(Q) (cd $(LOCAL_PATH); \
		find . -name Makefile -o -name Kconfig\* -o -name \*.pl \
		>> $(LINUX_BUILD_DIR)/sdksrcfiles)
	$(Q) (cd $(LOCAL_PATH); \
		find arch/$(LINUX_SRCARCH)/include include scripts -type f \
		>> $(LINUX_BUILD_DIR)/sdksrcfiles)
	$(Q) (cd $(LOCAL_PATH); \
		find arch/$(LINUX_SRCARCH)/kernel -type f -name '*.lds' \
		>> $(LINUX_BUILD_DIR)/sdksrcfiles)
$(if $(call streq,$(LINUX_ARCH),arm), \
	$(Q) (cd $(LOCAL_PATH); \
		find arch/$(LINUX_SRCARCH)/*/include -type f \
		>> $(LINUX_BUILD_DIR)/sdksrcfiles) \
)
$(if $(call streq,$(LINUX_ARCH),arm64), \
	$(Q) (cd $(LOCAL_PATH); \
		find arch/arm/include -type f \
		>> $(LINUX_BUILD_DIR)/sdksrcfiles) \
)
	$(Q) (cd $(LINUX_BUILD_DIR); \
		[ ! -d arch/$(LINUX_SRCARCH)/include ] || \
		find arch/$(LINUX_SRCARCH)/include include scripts .config Module.symvers -type f \
		>> $(LINUX_BUILD_DIR)/sdkobjfiles)
	$(Q) mkdir -p $(LINUX_SDK_DIR)
	$(Q) $(TAR) -C $(PRIVATE_PATH) -cf - -T $(LINUX_BUILD_DIR)/sdksrcfiles | \
		$(TAR) -C $(LINUX_SDK_DIR) -xf -
	$(Q) $(TAR) -C $(LINUX_BUILD_DIR) -cf - -T $(LINUX_BUILD_DIR)/sdkobjfiles | \
		$(TAR) -C $(LINUX_SDK_DIR) -xf -
	$(Q) rm -f $(LINUX_BUILD_DIR)/sdksrcfiles
	$(Q) rm -f $(LINUX_BUILD_DIR)/sdkobjfiles
	$(Q) echo "$(LINUX_ARCH)" > $(LINUX_SDK_DIR)/linuxarch
endef
