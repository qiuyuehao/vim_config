#!/bin/sh
apt-get install $@ -y
apt-get install -f
apt-get install $@ -y
