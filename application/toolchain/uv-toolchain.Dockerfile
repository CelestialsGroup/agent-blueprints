FROM ghcr.io/astral-sh/uv@sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47 AS uv
FROM python:3.14.6-bookworm@sha256:5dcba30b5f8fbd97e2f35dd1b140b3c94db70bd01b39ed88365732f8db8f68b5
COPY --from=uv /uv /usr/local/bin/uv
ENTRYPOINT ["uv"]
