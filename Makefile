
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

build: venv
	( \
	. venv/bin/activate; \
	poetry build; \
	deactivate;
	)

package: dist/turbostage
	version=`grep "__version__" turbostage/__init__.py | sed -e 's/^__version__ = "\(.*\)"$$/\1/'`; \
	zip -j turbostage-linux-v$${version}.zip dist/turbostage

dist/turbostage: venv turbostage/*.py pyproject.toml
	( \
	. venv/bin/activate; \
	poetry-dynamic-versioning; \
	pyinstaller --onefile --add-data "turbostage/content/splash.jpg:turbostage/content" -n turbostage turbostage/main.py; \
	deactivate; \
	)

.PHONY: test
test:
	python -m xmlrunner discover -o test-reports -s test

clean:
	${RM} -rf venv *~
