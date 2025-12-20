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

# Run a simulation with a rare-slow mixture distribution to generate data for the blog
.PHONY: run-rare-slow-mixture-simulation
run-rare-slow-mixture-simulation: dependencies-install
	$(VENV_PATH)/python sweep_plot.py --dist mixture --k 1 --mean-ms 10 --n 200000 \
  		--mix-p 0.01 --slow-mult 100 \
  		--rho-min 0.20 --rho-max 0.95 --rho-step 0.05 \
  		--out rare-slow-mixture-simulation.png --csv rare-slow-mixture-simulation.csv
