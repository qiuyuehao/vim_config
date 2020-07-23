#!/bin/env bash
# Dependencies: tesseract-ocr imagemagick gnome-screenshot xclip

#Name: OCR Picture
#Author:andrew
#Fuction: take a screenshot and OCR the letters in the picture
#Path: /home/Username/...
#Date: 2020-02-10

#you can only scan one character at a time
SCR="/home/qyh/Documents/temp"

####take a shot what you wana to OCR to text
gnome-screenshot -a -f $SCR.png

####increase the png
mogrify -modulate 100,0 -resize 400% $SCR.png
#should increase detection rate

####OCR by tesseract
tesseract $SCR.png $SCR &> /dev/null -l eng+chi1

####get the text and copy to clipboard
cat $SCR.txt | xclip -selection clipboard

exit
