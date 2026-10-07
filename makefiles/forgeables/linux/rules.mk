.PHONY: linux-config
linux-config:
	$(call __download_kernel)
	@echo "Configuring Linux Kernel"
	$(Q) $(MAKE) $(LINUX_MAKE_ARGS) $(TARGET_KERNEL_CONFIG)

.PHONY: linux
linux: linux-config
	@echo "Building Linux Kernel"
	$(Q) $(MAKE) $(LINUX_MAKE_ARGS) all
	$(Q) if grep -q "CONFIG_MODULES=y" $(LINUX_BUILD_DIR)/.config; then \
		$(MAKE) $(LINUX_MAKE_ARGS) modules_install ; \
	else \
		echo "CONFIG_MODULES not set in kernel config, ignoring"; \
	fi
	@mkdir -p $(STAGING_DIR)/boot
	$(call linux-copy-images)
	$(Q) $(MAKE) $(LINUX_MAKE_ARGS) dtbs_install
	$(Q) $(MAKE) $(LINUX_MAKE_ARGS) headers_install
	$(Q) cp -af $(LINUX_BUILD_DIR)/vmlinux $(STAGING_DIR)/boot
	$(Q) cp -af $(LINUX_BUILD_DIR)/.config $(LINUX_BUILD_DIR)/linux.config
	$(Q) echo "$(LINUX_ARCH)" > $(LINUX_BUILD_DIR)/linuxarch
	@echo "Linux kernel built"
