DOCKER_IMAGE_TAG ?= builder2-dev:latest

ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

.PHONY: setup_env
setup_env:
ifeq (,$(wildcard ${ROOT_DIR}/.venv/bin/python3))
	$(eval $(call vars,$@))
	rm -rf ${ROOT_DIR}/.venv
	python3 -m venv ${ROOT_DIR}/.venv
	${ROOT_DIR}/.venv/bin/pip3 install -e .[dev]
endif

.PHONY: clean
clean:
	rm -rf ${ROOT_DIR}/dist ${ROOT_DIR}/builder2.egg-info

.PHONY: build
build: setup_env clean
	${ROOT_DIR}/.venv/bin/python3 -m build ${ROOT_DIR}

.PHONY: build_docker
build_docker: build
	docker image build -f docker/Dockerfile -t ${DOCKER_IMAGE_TAG} --no-cache --progress plain .
