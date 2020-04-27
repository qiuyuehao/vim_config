#!/bin/sh
rm cscope* -rf
find ./ -name "*.c" -o -name "*.h" -o -name "*.cpp" > cscope.files
cscope -Rbkq -i cscope.files
rm cscope.files
