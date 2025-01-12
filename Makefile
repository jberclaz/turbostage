
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

build:
	poetry build

package:
	poetry-dynamic-versioning
	version=`grep "__version__" turbostage/__init__.py | sed -e 's/^__version__ = "\(.*\)"$$/\1/'`
	pyinstaller --onefile --add-data "turbostage/content/splash.jpg:turbostage/content" -n turbostage turbostage/main.py

clean:
	${RM} -rf venv *~
