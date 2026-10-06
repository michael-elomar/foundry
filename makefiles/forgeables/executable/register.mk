$(call module-add)

__mod := $(LOCAL_MODULE)

$(foreach __var,$(vars-LOCAL), \
	$(eval __modules.$(__mod).$(__var) := $(LOCAL_$(__var)))\
)

