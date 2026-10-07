# define here all the variables that could be
# included in a forge.mk file and include all
# the macros that could be called by the forge.mk file

# ========== Utility Variables ===========
MK_FILES := $(BUILD_SYSTEM)/makefiles
FORGEABLES := $(MK_FILES)/forgeables

# ========== General include =============
include $(MK_FILES)/vars.mk
include $(MK_FILES)/defs.mk

# ========== General variables ===========
CLEAR_VARS := $(MK_FILES)/clearvars.mk

# ========== Build variables =============
FORGE_EXECUTABLE := $(FORGEABLES)/executable/register.mk
RULES_EXECUTABLE := $(FORGEABLES)/executable/rules.mk

FORGE_LIBRARY := $(FORGEABLES)/library/register.mk
FORGE_SHARED_LIBRARY := $(FORGEABLES)/shared_library/register.mk
FORGE_STATIC_LIBRARY := $(FORGEABLES)/static_library/register.mk

FORGE_LINUX := $(FORGEABLES)/linux/register.mk
RULES_LINUX := $(FORGEABLES)/linux/rules.mk

FORGE_BUSYBOX := $(FORGEABLES)/busybox/register.mk
RULES_BUSYBOX := $(FORGEABLES)/busybox/rules.mk

include $(FORGEABLES)/common.mk

# include the product makefile and do the necessary steps
include product.mk
$(foreach __forge_mk,$(FORGE_MK_FILES), \
	$(info $(__forge_mk)) \
	$(eval include $(__forge_mk)) \
)

include $(FORGEABLES)/rules.mk

all: $(__modules)
