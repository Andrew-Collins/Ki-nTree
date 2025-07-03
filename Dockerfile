FROM python:3.12-slim AS build

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \ 
  apt update && apt install -y git
RUN --mount=type=cache,target=/root/.cache/pip \
  --mount=type=bind,source=.,target=/tmp/Ki-nTree/ pip install \
  /tmp/Ki-nTree

FROM python:3.12-slim

COPY --from=build /usr/local/lib/python3.12/site-packages/ /usr/local/lib/python3.12/site-packages/

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
  --mount=type=cache,target=/var/lib/apt,sharing=locked \ 
  apt update && apt install -y curl wget

ENTRYPOINT ["python", "-m", "kintree.kintree_cli"]
CMD ["--help"]
