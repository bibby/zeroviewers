FROM ubuntu:trusty
RUN apt-get update && apt-get install -y \
  python-dev \
  python-pip \
  supervisor

RUN pip install -U setuptools
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY app /opt/app

EXPOSE 3000

WORKDIR /opt/app/
CMD ["/usr/bin/supervisord"]
