
init: venv
	( \
	. venv/bin/activate; \
	pre-commit install; \
	deactivate; \
	)

venv: venv/.done

venv/.done: requirements.txt requirements-dev.txt
	python3 -m venv venv
	( \
	. venv/bin/activate; \
	pip3 install uv; \
	uv pip install -r requirements-dev.txt; \
	deactivate; \
	)
	touch venv/.done

clean:
	${RM} -rf venv *~
