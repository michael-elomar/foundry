ifneq ($(TARGET_BUSYBOX_CONFIG_FILE),)
.PHONY: busybox-config
busybox-config: linux
	$(call __download_busybox)
	$(call __create_dirs,$(BUSYBOX_BUILD_DIR))
	$(Q) $(MAKE) $(BUSYBOX_MAKE_ARGS) mrproper
	@cp $(TARGET_BUSYBOX_CONFIG_FILE) $(BUSYBOX_BUILD_DIR)/.config
	$(Q) $(MAKE) $(BUSYBOX_MAKE_ARGS) oldconfig
else
.PHONY: busybox-config
busybox-config: linux
	@echo "THIS SHOULD NOT BE PRINTED"
	$(Q) $(MAKE) $(BUSYBOX_MAKE_ARGS) defconfig
endif

.PHONY: busybox
busybox: busybox-config
	@echo "Building busybox"
	$(Q) $(MAKE) $(BUSYBOX_MAKE_ARGS)
	$(Q) $(MAKE) $(BUSYBOX_MAKE_ARGS) install
	$(call __copy_skel,$(SKEL_PATH))

