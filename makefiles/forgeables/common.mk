$(call __check-local-vars $(FORGE_MK))

OUT_DIR := $(WORKSPACE)/out/
BUILD_DIR := $(OUT_DIR)/build
OBJ_DIR := $(BUILD_DIR)/obj

TARGET_PRODUCT_OUT_DIR = $(OUT_DIR)/$(TARGET_PRODUCT)
TARGET_STAGING_DIR := $(TARGET_PRODUCT_OUT_DIR)/staging
TARGET_ETC_DIR := $(TARGET_PRODUCT_OUT_DIR)/etc
TARGET_USR_DIR := $(TARGET_PRODUCT_OUT_DIR)/usr
TARGET_BIN_DIR := $(TARGET_USR_DIR)/bin
TARGET_SBIN_DIR := $(TARGET_USR_DIR)/sbin
TARGET_LIB_DIR := $(TARGET_USR_DIR)/lib
TARGET_SLIB_DIR := $(TARGET_USR_DIR)/slib
TARGET_INCLUDE_DIR := $(TARGET_USR_DIR)/include

DIRS := \
	$(OUT_DIR) \
	$(BUILD_DIR) \
	$(OBJ_DIR) \
	$(TARGET_PRODUCT_OUT_DIR) \
	$(TARGET_STAGING_DIR) \
	$(TARGET_ETC_DIR) \
	$(TARGET_USR_DIR) \
	$(TARGET_BIN_DIR) \
	$(TARGET_SBIN_DIR) \
	$(TARGET_LIB_DIR) \
	$(TARGET_SLIB_DIR) \
	$(TARGET_INCLUDE_DIR)

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

# To be able to use ccache with pre-compiled headers, some environment
# variables are required
CCACHE :=
ifeq ("$(USE_CCACHE)","1")
  ifneq ("$(shell which ccache 2>/dev/null)","")
    export CCACHE_SLOPPINESS := time_macros
    CCACHE := ccache
    TARGET_GLOBAL_CFLAGS += -fpch-preprocess
    HOST_GLOBAL_CFLAGS += -fpch-preprocess
  endif
endif
