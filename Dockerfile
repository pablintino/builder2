FROM python:3.10.5-slim-bullseye


ARG BUILDER_INSTALLATION=/tools
ARG BUILDER_CUSTOM_CERTS=/tools/ssl
ARG BUILDER_MAX_CPU_COUNT=10
ARG BUILDER_TIMEOUT_MULTIPLIER=100
ENV BUILDER_INSTALLATION $BUILDER_INSTALLATION
ENV BUILDER_CUSTOM_CERTS $BUILDER_CUSTOM_CERTS

# Install conan and init the default profile
RUN pip3 install conan && conan config init && conan profile update settings.compiler.libcxx=libstdc++11 default

COPY builder2 /tools/scripts/builder2
COPY scripts /tools/scripts
COPY requirements.txt /tools/scripts/builder2/requirements.txt
COPY toolchain-metadata.json /tools/scripts/builder2/toolchain-metadata.json
ENV PATH="/tools/scripts:${PATH}"

RUN pip3 install -r /tools/scripts/builder2/requirements.txt && \
    /tools/scripts/builder2/builder2 install -f /tools/scripts/builder2/toolchain-metadata.json  \
    -j $BUILDER_MAX_CPU_COUNT \
    -t $BUILDER_TIMEOUT_MULTIPLIER \
    -d $BUILDER_INSTALLATION

ENTRYPOINT ["/tools/scripts/entrypoint"]
CMD ["/bin/bash"]