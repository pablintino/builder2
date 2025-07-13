FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install --assume-yes --no-install-recommends \
		ca-certificates \
        python3 \
        python3-pip \
        python3-venv

COPY dist/*.whl /opt/builder2/
COPY docker/entrypoint /usr/local/bin/builder2-entrypoint

RUN python3 -m venv /opt/builder2/.venv && \
    /opt/builder2/.venv/bin/pip3 install `find /opt/builder2 -type f -name "*.whl"` && \
    ln -s /opt/builder2/.venv/bin/builder2 /usr/local/bin/builder2 && \
    rm -f /opt/builder2/*.whl

ENTRYPOINT ["/usr/local/bin/builder2-entrypoint"]
CMD ["/bin/bash"]
