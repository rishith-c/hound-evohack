#!/bin/sh
# url.sh — print the remote's public link, key included. It changes whenever the Pi (or its tunnel) restarts.
#   sh pi/url.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PI="${PI_HOST:-$(sh "$DIR/find_pi.sh")}"
command ssh -o ConnectTimeout=5 -o BatchMode=yes "$PI" 'sh ~/rover/tunnel_url.sh'
