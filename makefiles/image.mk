MKFS_SCRIPT := $(BUILD_SYSTEM)/scripts/mkimg.py

.PHONY: image
image:
	@$(MKFS_SCRIPT) --partitions fat32 100M ext2 500M --output $(OUT_DIR)/avalon.img
