#!/usr/bin/python3
import csv
#-*-coding:utf-8-*-
line_counter = 0
page_index = 0
i2c_addr = 0
strlist = []
for i  in range(10 * 256):
    strlist.append(" ")

page_func_list = ["", "", "", "", "", "", "", "", "", ""]
for i in range(10):
    page_func_list[i] = "void make_page_%d_data(void)\n" % i + "{\n"
    page_func_list[i] += "\tswitch (i2c_addr) {\n"
func_file = open("./func_make_data.c", "w")
with open('./i2c_poweron.csv', 'r') as f:
    raw_list = []
    rander = csv.reader(f)
    for i in rander:
        line_counter = line_counter + 1
        if len(i) > 9:
            if i[7] != "None" and (i[6] == "SP" or i[6] == "S") :
                lens = i[4]
                lens = lens.strip("B")
                lens = int(lens)
                byte_str = i[9].strip("*")
                #print(byte_str)
                if i[8] == "Write Transaction" and lens >= 2 and byte_str.split(" ")[0] != "FF":
                    print("write data found line:" , line_counter, "page", page_index, "i2c_addr:%x" % i2c_addr,"len:", lens,"data:", byte_str)
                if i[8] == "Write Transaction" and lens == 2:
                    if byte_str.split(" ")[0] == "FF":
                        #print("line :%d this is a write, and set page %d" % (line_counter,page_index))
                        page_index = int(byte_str.split(" ")[1])
                if i[8] == "Write Transaction" and lens == 1:
                    i2c_addr = int(byte_str.split(" ")[0], 16)
                    #print("this is a set i2c addr")
                    pass
                if i[8] == "Read Transaction":
                    #newByteStr = byte_str.replace(" ", ",")
                    tmp_array = byte_str.split(" ")
                    newString = ""
                    for k in tmp_array:
                        k = "0x" + k + ","
                        newString += k
                    newString = newString[:-1]
                    #print(newByteStr)
                    if (strlist[page_index * 256 + i2c_addr] != newString):
                        if strlist[page_index * 256 + i2c_addr] != "":
                            print("conflict data found line " , line_counter, "page", page_index, "i2c_addr:%x" % i2c_addr,"len:", lens,"data:",byte_str)
                        page_func_list[page_index] += "\t\tcase %x" % i2c_addr + ":\n"
                        page_func_list[page_index] += "\t\t{\n" + "\t\t\tuint8 char t[] = {" + newString + "};\n"
                        page_func_list[page_index] += "\t\t\tmemcpy(make_data, t, sizeof(t));\n"
                        page_func_list[page_index] += "\t\t\tmakedata_len = %d;\n" % lens
                        page_func_list[page_index] += "\t\t" + "}\n"
                        page_func_list[page_index] += "\t\t" + "break;\n"
                        strlist[page_index * 256 + i2c_addr] = newString
                    else:
                        pass
                        #print("same value found!!!")
    for i in range(10):
        #print(page_func_list[i])
        page_func_list[i] += "\t\tdefault:\n"
        page_func_list[i] += "\t\tbreak;\n"
        page_func_list[i] += "\t}\n"
        page_func_list[i] += "}\n"
        func_file.write(page_func_list[i])
    func_file.close()


