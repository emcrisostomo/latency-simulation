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
run-cs-sweep-plot:
	$(VENV_PATH)/python sweep_plot.py --sweep cs --dist lognormal --rho 0.7 --cs-min 0.5 --cs-max 4.0 --cs-step 0.1 --n 500000 --out sweep_cs.png

.PHONY: pdf
pdf:
	pandoc -o blog-post.pdf blog-post.md --from markdown --listings --toc --toc-depth=2 --number-sections