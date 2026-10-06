$(call module-add)

$(info adding $(LOCAL_MODULE))

$(foreach __var,$(vars-LOCAL), \
	$(eval __modules.$(LOCAL_MODULE).$(__var) := $(LOCAL_$(__var))) \
)

