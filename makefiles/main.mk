# define here all the variables that could be
# included in a forge.mk file and include all
# the macros that could be called by the forge.mk file

# ========== Utility Variables ===========
MAKEFILES := $(BUILD_SYSTEM)/makefiles
FORGEABLES := $(MAKEFILES)/forgeables

# ========== General include =============
include $(MAKEFILES)/vars.mk
include $(MAKEFILES)/defs.mk

# ========== General variables ===========
CLEAR_VARS := $(MAKEFILES)/clearvars.mk


# ========== Build variables =============

FORGE_EXECUTABLE := $(FORGEABLES)/executable/register.mk
FORGE_LIBRARY := $(FORGEABLES)/library/register.mk
FORGE_SHARED_LIBRARY := $(FORGEABLES)/shared_library/register.mk
FORGE_STATIC_LIBRARY := $(FORGEABLES)/static_library/register.mk

include $(FORGE_MK)

$(info $(__modules))
$(foreach __mod,$(__modules), \
	$(foreach __var,$(vars-LOCAL), \
		$(info __modules.$(__mod).$(__var): $(__modules.$(__mod).$(__var))) \
))
