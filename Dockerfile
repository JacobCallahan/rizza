FROM python:3
MAINTAINER https://github.com/JacobCallahan

RUN mkdir rizza
COPY / /root/rizza/
RUN cd /root/rizza && python3 setup.py install

WORKDIR /root/rizza

ENTRYPOINT ["rizza"]
CMD ["--help"]
