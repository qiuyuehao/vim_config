#!/bin/sh
sudo apt-get install $1 -y
sudo apt-get install -f
sudo apt-get install $1 -y
