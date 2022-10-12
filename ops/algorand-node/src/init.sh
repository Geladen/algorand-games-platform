#!/bin/sh

set -e

mkdir -p /var/lib/algorand && cp -r /home/algo/node/. /var/lib/algorand/ &&\
chmod -R 700 /var/lib/algorand/kmd && /bin/algod -d /var/lib/algorand -l 0.0.0.0:$PORT_ALGOD
