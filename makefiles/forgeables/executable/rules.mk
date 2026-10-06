# include $(BUILD_SYSTEM)/makefiles/forgeables/common.mk

LOCAL_MODULE_TYPE := Executable

# target creation fore executable target

define executable-target

obj := $(call __convert_to_obj,$(__modules.$(1).SRC_FILES),$(OBJ_DIR))

$(info $(__modules.$(1).SRC_FILES))

$(obj): $(__modules.$(1).SRC_FILES)
	@$(call __build_step_banner,"Compiling",$(1))
	@$(foreach f,$(__modules.$(1).SRC_FILES),\
		$(call __print_banner1,$(TARGET_ARCH) $(call __get_lang,$f),$(1),$f))
	@$(CXX) -c $(_effective_CXXFLAGS) $< -o $@

$(1): $(obj)
	@$(call __build_step_banner,"Linking",$(1))
	@$(CXX) $(_external_add_LDFLAGS) $< -o $(BIN_DIR)/$@
	@$(call __print_banner2,"$(LOCAL_MODULE_TYPE)",$@,$(BIN_DIR)/$@)
	@$(call __print_green,"Done building $(1)")
endef

#
# $(foreach __mod,$(__modules), \
#   $(eval $(call executable-target,$(__mod))) \
# )
