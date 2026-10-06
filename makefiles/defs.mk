## Useful macros to be used later

# Empty variable and space (useful for pretty prinf of messages)
empty :=
space := $(empty) $(empty)
space4 := $(space)$(space)$(space)$(space)

# True/False values. Any non-empty test is considered as True
true := T
false :=

streq = $(if $(filter-out xx,x$(subst $1,,$2)$(subst $2,,$1)x),$(false),$(true))


# Modules database
__modules := $(empty)

# Get all defined LOCAL_XXX variables
__get-defined-local-vars = $(filter LOCAL_%,$(.VARIABLES))

# Check all defined LOCAL_XXX VARIABLES.
# $1 is the forge.mk that is being processed
__check-local-vars = \
	$(foreach __v,$(__get-defined-local-vars), \
		$(call __check-local-var,$1,$(__v)) \
	)

# Check a LOCAL_XXX variable for validity, clear it if unknown to the system
# for each LOCAL_XXX, remove the 'LOCAL_' and check if XXX is defined present in __all-vars-LOCAL
__check-local-var = \
	$(if $(value $2), \
		$(if $(filter $(patsubst LOCAL_%,%,$2),$(__all-vars-LOCAL)),$(empty), \
			$(warning $1: discarding unknown LOCAL variable $2) \
			$(eval $2 :=) \
	))

# remove -I if it was added in the forge.mk file and prepend -I
__prepend-I-flag = $(strip \
	$(foreach __inc,$1,\
		$(addprefix -I,$(patsubst -I%,%,$(__inc))) \
	))

__convert_to_obj = $(strip \
	$(foreach _src,$1,\
		$(addprefix $2/,$(basename $(notdir $(_src))).o) \
))

__create_dirs = \
	$(info Preparing build directories) \
	$(foreach _dir,$1,\
		$(shell mkdir -p $(_dir)) \
)
# Get the path of the current directory from which 'forge' is being called
my-path = $(shell pwd)

# Add module to the build system
module-add = \
	$(eval LOCAL_MODULE := $(strip $(LOCAL_MODULE))) \
	$(if $(LOCAL_MODULE),$(empty), \
		$(error $(LOCAL_PATH): LOCAL_MODULE is not defined)) \
	$(eval __mod := $(LOCAL_MODULE)) \
	$(eval __add := 1) \
	$(if $(call streq,$(__clear-vars-called),0), \
		$(error $(LOCAL_PATH): $(__mod): missiong include $$(CLEAR_VARS)) \
	) \
	$(if $(call streq,$(__add),1), \
		$(eval __modules += $(__mod)) \
	) \
	$(eval __clear-vars-called := 0)


###############################################################################
# Print macros

# ANSI color codes
RED     	 	:= \033[0;31m
BOLD_RED     	:= \033[0;31;1m
GREEN   	 	:= \033[0;32m
BOLD_GREEN 	 	:= \033[0;32;1m
YELLOW  	 	:= \033[0;33m
BLUE    	 	:= \033[0;34m
PURPLE  		:= \033[0;35m
MAGENTA 		:= \033[1;35m
CYAN    		:= \033[0;36m
RESET   		:= \033[0m

__print_color = \
	@echo "$(1)$(2)$(RESET)"

__print_red = \
	$(call __print_color,$(BOLD_RED),$1)

__print_green = \
	$(call __print_color,$(GREEN),$1)

__print_yellow = \
	$(call __print_color,$(YELLOW),$1)

__print_cyan = \
	$(call __print_color,$(CYAN),$1)

__print_purple = \
	$(call __print_color,$(PURPLE),$1)

__get_lang = \
	$(if $(filter $(suffix $1),.c),C, \
        $(if $(filter $(suffix $1),.cpp .cc),C++,Unknown))

COLOR_TOOL 		:= $(PURPLE)
COLOR_MODULE 	:= $(CYAN)
COLOR_FILE 		:= $(YELLOW)

define __build_step_banner
	echo "$(COLOR_TOOL)$1$(RESET): $(COLOR_MODULE)$2$(RESET)"
endef

define __print_banner1
	echo "$(COLOR_TOOL)$1: $(RESET)$(COLOR_MODULE)$2$(RESET) <= $(COLOR_FILE)$3$(RESET)"
endef

define __print_banner2
	echo "$(COLOR_TOOL)$1: $(RESET)$(COLOR_MODULE)$2$(RESET) => $(COLOR_FILE)$3$(RESET)"
endef

define __get_extension
	echo $(suffix $1)
endef
