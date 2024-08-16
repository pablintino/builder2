FROM debian:bookworm-slim

RUN apt-get update && apt-get install --assume-yes --no-install-recommends \
		ca-certificates \
        python3 \
        python3-pip && pip3 install pip --upgrade


COPY dist/*.whl /opt/builder2/pip/
RUN pip install `find /opt/builder2/pip -type f -name "*.whl"`
