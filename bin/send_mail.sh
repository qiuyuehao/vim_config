#/bin/sh

if [ $# -gt 1 ]; then
	echo "$2" | mutt -s "$1" scutqyh@163.com
elif [ $# -eq 1 ]; then
	echo "$1" | mutt -s "$1" scutqyh@163.com
else
	echo "something done in your linux command line" | mutt -s "something done in your linux command line" scutqyh@163.com
fi