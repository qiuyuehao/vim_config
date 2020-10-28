#!/bin/sh
git add *
if [ $# -eq 1 ];then
	git commit -m "$1"
else
	git commit -m "quick commit, save something"
fi
git push origin -u
