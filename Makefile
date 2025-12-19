VENV_PATH = .venv/bin
PIP_COMPILE_PATH = $(VENV_PATH)/pip-compile
PIP_COMPILE = $(PIP_COMPILE_PATH) --strip-extras -r requirements.in

.PHONY: dependencies-compile
dependencies-compile: pip-tools requirements.txt

.PHONY: pip-tools
pip-tools:
	if [[ ! -x $(PIP_COMPILE_PATH) ]] ; then \
		$(VENV_PATH)/pip install pip-tools ; \
	fi  

requirements.txt: requirements.in
	$(PIP_COMPILE)

.PHONY: dependencies-install
dependencies-install: dependencies-compile
	$(VENV_PATH)/pip install -r requirements.txt

.PHONY: requirements-update
requirements-update:
	$(PIP_COMPILE)
