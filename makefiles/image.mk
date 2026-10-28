MKFS_SCRIPT := $(BUILD_SYSTEM)/scripts/mkimg.py

.PHONY: image
image:
	@$(MKFS_SCRIPT) --partitions \
		fat32 200M $(TARGET_STAGING_DIR)/boot \
		ext2 500M $(TARGET_STAGING_DIR) \
		--output $(TARGET_PRODUCT_OUT_DIR)/avalon.img


