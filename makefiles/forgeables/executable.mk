include $(BUILD_SYSTEM)/makefiles/forgeables/common.mk

LOCAL_MODULE_TYPE := Executable


$(call module-add)
# $(info $(__modules))

OBJFILES = $(call __convert_to_obj,$(LOCAL_SRC_FILES),$(OBJ_DIR))

$(OBJFILES): $(LOCAL_SRC_FILES)
	@$(call __build_step_banner,"Compiling",$(LOCAL_MODULE))
	@$(foreach f,$(LOCAL_SRC_FILES),\
		$(call __print_banner1,$(TARGET_ARCH) $(call __get_lang,$f),$(LOCAL_MODULE),$f))
	@$(CXX) -c $(_effective_CXXFLAGS) $< -o $@

$(LOCAL_MODULE): $(OBJFILES)
	@$(call __build_step_banner,"Linking",$(LOCAL_MODULE))
	@$(CXX) $(_external_add_LDFLAGS) $< -o $(BIN_DIR)/$@
	@$(call __print_banner2,"$(LOCAL_MODULE_TYPE)",$@,$(BIN_DIR)/$@)
	@$(call __print_green,"Done building $(LOCAL_MODULE)")

