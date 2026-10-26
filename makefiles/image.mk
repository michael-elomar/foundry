MKFS_SCRIPT := $(BUILD_SYSTEM)/scripts/mkimg.py

.PHONY: image
image:
	@$(MKFS_SCRIPT) --partitions \
		fat32 100M $(STAGING_DIR)/boot \
		ext2 500M $(STAGING_DIR) \
		--output $(OUT_DIR)/avalon.img


