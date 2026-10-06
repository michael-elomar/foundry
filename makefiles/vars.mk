vars-LOCAL :=
macros-LOCAL :=


# Variable for the local path of current project
vars-LOCAL += PATH

# Variable name of the module to be built: executable, library, etc. See forgeables.
vars-LOCAL += MODULE

# Variable name to hold the type of the module being built.
vars-LOCAL += MODULE_TYPE

# Variable containing all the library dependencies
vars-LOCAL += LIBRARY

# Variable for the assembler flags
vars-LOCAL += ASFLAGS

# Variable containing all the cflags passed to cc
vars-LOCAL += CFLAGS

# Variable containing al the ldflags passed to the linker
vars-LOCAL += LDFLAGS

# Variable containing all the -L paths for the library dependecies
vars-LOCAL += LDPATHS

# Variable containing all the -l flags for the library dependencies
vars-LOCAL += LDLIBS

# Module description Variable
vars-LOCAL += DESCRIPTION

# Variable for source files to be compiled.
# Supported files .c, .cc, .cpp
vars-LOCAL += SRC_FILES

# Variable for the include directories.
# Do not write '-I' flag when defining this variable
# it will be prepended by the build system
vars-LOCAL += INCLUDE

# Category path for the module: bin, lib, system, etc
vars-LOCAL += CATEGORY_PATH


__all-vars-LOCAL := \
	$(vars-LOCAL) \
	$(macros-LOCAL)
