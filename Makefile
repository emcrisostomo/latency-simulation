UV ?= uv
VENV_ROOT ?= .venv
VENV_PATH := $(VENV_ROOT)/bin
VENV_PYTHON := $(VENV_PATH)/python

.PHONY: default
default: dependencies-install

.PHONY: create-venv
create-venv:
	[ -x "$(VENV_PYTHON)" ] || $(UV) venv $(VENV_ROOT)

.PHONY: dependencies-compile
dependencies-compile: requirements.txt

requirements.txt: requirements.in | create-venv
	$(UV) pip compile --python $(VENV_PYTHON) requirements.in -o requirements.txt

.PHONY: dependencies-install
dependencies-install: requirements.txt | create-venv
	$(UV) pip sync --python $(VENV_PYTHON) requirements.txt

.PHONY: requirements-update
requirements-update: | create-venv
	$(UV) pip compile --upgrade --python $(VENV_PYTHON) requirements.in -o requirements.txt

# Run a simulation with a rare-slow mixture distribution to generate data for the blog
.PHONY: run-rare-slow-mixture-simulation
run-rare-slow-mixture-simulation: dependencies-install
	$(VENV_PATH)/python sweep_plot.py --dist mixture --k 1 --mean-ms 10 --n 200000 \
  		--mix-p 0.01 --slow-mult 100 \
  		--rho-min 0.20 --rho-max 0.95 --rho-step 0.05 \
  		--out rare-slow-mixture-simulation.png --csv rare-slow-mixture-simulation.csv

# Run sweeps for each distribution and generate plots and CSVs
.PHONY: run-sweep-for-each-distribution-and-output-graph
run-sweep-for-each-distribution-and-output-graph: dependencies-install
	$(VENV_PATH)/python sweep_plot.py --dist const                                  --out sweep_const.png     --csv sweep_const.csv
	$(VENV_PATH)/python sweep_plot.py --dist exp                                    --out sweep_exp.png       --csv sweep_exp.csv
	$(VENV_PATH)/python sweep_plot.py --dist lognormal --lognorm-sigma 1.2          --out sweep_lognorm.png   --csv sweep_lognorm.csv
	$(VENV_PATH)/python sweep_plot.py --dist mixture   --mix-p 0.01 --slow-mult 100 --out sweep_mix.png       --csv sweep_mix.csv

.PHONY: run-sweep-for-each-distribution
run-sweep-for-each-distribution: dependencies-install
	$(VENV_PATH)/python queue_sim.py --dist const     --rho 0.8 --mean-ms 10 --n 200000
	$(VENV_PATH)/python queue_sim.py --dist exp       --rho 0.8 --mean-ms 10 --n 200000
	$(VENV_PATH)/python queue_sim.py --dist mixture   --rho 0.8 --mean-ms 10 --n 200000 --mix-p 0.01        --slow-mult 100 
	$(VENV_PATH)/python queue_sim.py --dist lognormal --rho 0.8 --mean-ms 10 --n 200000 --lognorm-sigma 1.2

.PHONY: run-cs-sweep-plot
run-cs-sweep-plot: dependencies-install
	$(VENV_PATH)/python sweep_plot.py --sweep cs --dist lognormal --rho 0.7 --cs-min 0.5 --cs-max 4.0 --cs-step 0.1 --n 500000 --out sweep_cs.png

.PHONY: run-retries-plot
run-retries-plot: dependencies-install
	$(VENV_PATH)/python sweep_plot.py --sweep retries --dist const --mean-ms 10 --retry-p 0.3 --rho-min 0.2 --rho-max 0.7 --rho-step 0.05 --out sweep_retries.png --n 500000

.PHONY: pdf
pdf: blog-post.pdf practical-appendix.pdf

blog-post.pdf: blog-post.md
	pandoc -o blog-post.pdf          blog-post.md          --from markdown --toc --toc-depth=2 --number-sections

practical-appendix.pdf: practical-appendix.md
	pandoc -o practical-appendix.pdf practical-appendix.md --from markdown --toc --toc-depth=2 --number-sections
