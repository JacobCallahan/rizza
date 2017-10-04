FROM python:3
MAINTAINER https://github.com/JacobCallahan

RUN mkdir rizza
COPY / /root/rizza/
RUN cd /root/rizza && python3 setup.py install
RUN mkdir -p /root/.config/nailgun
RUN cp /root/rizza/config/server_configs.json /root/.config/nailgun/

WORKDIR /root/rizza

ENTRYPOINT ["rizza"]
CMD ["--help"]
