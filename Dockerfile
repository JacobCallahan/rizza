FROM python:3
MAINTAINER https://github.com/JacobCallahan

RUN mkdir rizza
COPY / /root/rizza/
RUN cd /root/rizza && pip install . --upgrade

WORKDIR /root/rizza

ENTRYPOINT ["rizza"]
CMD ["--help"]
