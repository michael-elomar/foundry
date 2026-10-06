$(call __check-local-vars $(FORGE_MK))

OUT_DIR := out

BUILD_DIR := $(OUT_DIR)/build

STAGING_DIR := $(OUT_DIR)/staging

OBJ_DIR := $(BUILD_DIR)/obj

BIN_DIR := $(STAGING_DIR)/bin

LIB_DIR := $(STAGING_DIR)/lib

DIRS := \
	$(OUT_DIR) \
	$(BUILD_DIR) \
	$(STAGING_DIR) \
	$(OBJ_DIR) \
	$(BIN_DIR) \
	$(LIB_DIR)

$(call __create_dirs,$(DIRS))

# Define compiler path if not defined inside forge.mk

# TARGET_CC is path to gcc with prefix included
# e.g. TARGET_CC = /path/to/compiler/prefix- like arm-none-eabi-

CC := gcc
CXX := g++
AS := gcc -x assembler-with-cpp
OBJCOPY := objcopy
SZ := size

ifdef TARGET_CC
CC := $(TARGET_CC)/$(CC)
CXX := $(TARGET_CC)/$(CXX)
AS := $(TARGET_CC)/$(AS)
OBJCOPY := $(TARGET_CC)/$(OBJCOPY)
SZ := $(TARGET_CC)/$(SZ)
endif

ifndef TARGET_ARCH
TARGET_ARCH := x64
endif

_effective_CFLAGS := $(LOCAL_CFLAGS) \
	$(call __prepend-I-flag,$(LOCAL_INCLUDE))

_effective_CXXFLAGS := \
	$(filter-out -std=%,$(_effective_CFLAGS)) \
	$(LOCAL_CXXFLAGS)

_external_add_ASFLAGS := \
	$(LOCAL_ASFLAGS)

_external_add_LDFLAGS := \
	$(LOCAL_LDFLAGS) \
	$(LOCAL_LDPATHS) \
	$(LOCAL_LDLIBS)
