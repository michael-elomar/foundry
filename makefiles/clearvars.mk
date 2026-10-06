__clear-var = \
	$(eval $1 :=)

__clear-vars = \
	$(foreach __var,$1,\
		$(if $(filter PATH,$(__var)),, \
			$(call __clear-var,LOCAL_$(__var) \
	)))

$(call __clear-vars,$(__all-vars-LOCAL))

__clear-vars-called := 1
