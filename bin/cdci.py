#!/usr/bin/python3

import os, sys
import re
import time
import subprocess
import usb.core, usb.util  # pyusb
import zlib
import array
import struct
import sys
import socket
import ctypes as ct
rx_cnt = 18
tx_cnt =  36
lst_file_path = None
img_file_path = None

class ImageFileError(Exception):
    pass

class ImageFileReadError(ImageFileError):
    pass

class ImageFileWriteError(ImageFileError):
    pass

class TouchBootImageFile(object):
    """Representation of a TouchBoot image file.

       This class stores the Flash areas and JSON files that go into
       an image file. It can read or write image files to disk and
       construct them programmatically.
    """

    def __init__(self):
        """Create a new empty TouchBootImageFile object."""
        self.flashAreas = []
        self.jsonSection = None

    def addFlashArea(self, name, address, data, flags, length,crc):
        """Add a flash area.

           Arguments
             - name : the name of the area (max 16 characters).
             - address : the word address of the area in flash.
             - data : array of 16-bit words with area contents.
             - flags : dictionary of boolean flag values. The only
                       flag supported is "always overwrite".
        """

        area = {'name' : name,
                'address' : address,
                'data' : data,
                'flags' : flags,
                'length' : length,
                'crc' : crc,
               }
        self.flashAreas.append(area)

    def getFlashArea(self, name):
        """Returns specified flash area contents.

           Arguments
             - name : the name of the area to retrieve.

           Return value

             If the area does not exist, return None. If the area does
             exist, return a dict with the fields 'name', 'address',
             'data', and 'flags' which have the same format as the
             addFlashArea arguments of the same names.
        """

        for area in self.flashAreas:
            if name == area['name']:
                return area
        return None

    def setJSONSection(self, jsonData):
        """Puts the specified data in the JSON section.

           Arguments
             - jsonData: JSON data stored as a string.
        """

        self.jsonSection = jsonData

    def getJSONSection(self):
        """Returns the contents of the JSON section (or None if empty)."""

        return self.jsonSection

    def save(self, filename):
        """Writes a TouchBoot image file with the object's contents.

           Arguments
             - filename : the file name to use for the output file.
        """

        f = open(filename, 'wb')
        f.write(struct.pack('<L', 0x4818472B))
        sections = len(self.flashAreas) + (0 if self.jsonSection is None else 1)
        f.write(struct.pack('<L', sections))

        offset = 8 + 4 * sections
        for area in self.flashAreas:
            f.write(struct.pack('<L', offset))
            offset += 36 + len(area['data'])*2

        if self.jsonSection is not None:
            f.write(struct.pack('<L', offset))

        for area in self.flashAreas:
            f.write(struct.pack('<L', 0x7C05E516))
            idString = ("%-16s" % area['name'])[0:16]
            f.write(idString.encode('ascii', 'ignore'))
            flags = 0
            if area['flags'].get('alwaysOverwrite', False):
                flags |= 1

            f.write(struct.pack('<L', flags))
            f.write(struct.pack('<L', area['address']))
            f.write(struct.pack('<L', len(area['data'])*2))

            data = array.array('H', area['data'])
            if sys.version_info[0] == 3:
                data = data.tobytes()
            else:
                data = data.tostring()
            crc = zlib.crc32(data) & 0xFFFFFFFF
            f.write(struct.pack('<L', crc))
            f.write(data)

        if self.jsonSection is not None:
            compressedJsonData = zlib.compress(self.jsonSection, 9)
            f.write(struct.pack('<L', 0xC1FB41D8))
            f.write(struct.pack('<L', len(compressedJsonData)))
            f.write(compressedJsonData)

    @staticmethod
    def load(filename):
        """Create a TouchBootImageFile object from a file.

           Arguments
             - filename : the file to load.

           Return value
             A new TouchBootImageFile object.
        """

        f = open(filename, 'rb')
        obj = TouchBootImageFile()

        # check header

        magic = struct.unpack('<L', f.read(4))[0]
        if magic != 0x4818472B:
            raise ImageFileReadError('Bad magic value 0x%08X != 0x4818472B\n', magic)

        sections = struct.unpack('<L', f.read(4))[0]
        offsets = []
        for s in range(sections):
            offsets.append(struct.unpack('<L', f.read(4))[0])

        for addr in offsets:
            f.seek(addr)

            magic = struct.unpack('<L', f.read(4))[0]
            if magic == 0x7C05E516: # Flash area
                name = f.read(16).decode('ascii').rstrip()
                rawFlags = struct.unpack('<L', f.read(4))[0]
                flags = {
                    'alwaysOverwrite' : (rawFlags & 1) == 1
                    }
                destAddr = struct.unpack('<L', f.read(4))[0]
                length = struct.unpack('<L', f.read(4))[0]
                crc = struct.unpack('<L', f.read(4))[0]
                #print(name, str(hex(crc)))
                data = f.read(length)
                #print(type(data))
                if crc != zlib.crc32(data) & 0xFFFFFFFF:
                    raise ImageFileReadError("CRC mismatch in flash area %s" % name)

                #data = array.array('H', data).tolist()
                data = bytearray(data)
                obj.addFlashArea(name, destAddr, data, flags, length,crc)

            elif magic == 0xC1FB41D8: # JSON area
                length = struct.unpack('<L', f.read(4))[0]
                jsonData = zlib.decompress(f.read(length))

                obj.setJSONSection(jsonData)

            else:
                raise ImageFileReadError("Unknown section type: %08X" % magic)

        return obj

STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11
STD_ERROR_HANDLE = -12

VDDH_VOLTAGE = 3300
VDDIO_VOLTAGE = 1800

SPI_MODE = 3
SPI_SPEED = 1000

NORMAL_SLEEP_TIME=0.1

class Comm2:
    def __init__(self,
                 ip='localhost',
                 busAddr=None,
                 vddh=3300,
                 vddio=1800,
                 debug=False):

        self.voltage = {"vled": vddh, "vdd": vddio, "vddtx": 1800, "vpu": 1800}
        self.interface = ip
        #self.port = 10001 # for redremote
        self.busAddr = busAddr

        self.retry = 5 # retry r/w times
        self.rmi_mode = False
        if self.interface == 'i2c':
            self.prefix = 'target=0 raw bus-addr={}'.format(self.busAddr)
        else:
            self.prefix = 'target=0 raw'

        self.debug = debug

        if self.interface == 'i2c' or self.interface == 'spi':
            self.usb = usb.core.find(idVendor=0x06CB, idProduct=0x000F)
            if self.usb is None:
                print('Cannot connect to mpc04, make sure it\'s plugged in USB port.')
                self.connected = False
                return

            self.out_endpoint_addr = 0x1
            self.in_endpoint_addr = 0x82
            self.usb.set_configuration()

            # get an endpoint instance
            cfg = self.usb.get_active_configuration()
            intf = cfg[(0, 0)]
            self.ep_in = usb.util.find_descriptor(
              intf,
              # match the first IN endpoint
              custom_match= \
                lambda e: \
                  usb.util.endpoint_direction(e.bEndpointAddress) == \
                  usb.util.ENDPOINT_IN)

            if self.ep_in == None:
                print("Error: USB endpoint_in Error")
                self.connected = False
                return

            self.connected = True
        else:
             #===== initial socket =====
            print("connect use red remote")
            self.ip = bytes("127.0.0.1", 'utf-8')
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                result = self.socket.connect((self.ip, 10001))
            except:
                self.connected = False
                print(
                    'Cannot connect to redremote server, make sure RedRemote is running.'
                )
                return
             #設定recv的timeout時間
            print("connect result", result)
            self.socket.settimeout(0.2)
            self.connected = True
            pass

        # Init device
        self.DeviceInit()
        self.tcmDevice = True
        return
        r = self.readMsg()
        if r == None:
            self.tcmDevice = False
            return
        else:
            self.tcmDevice = True

        # read extra-command that didn't finished for last connection (For A511(2d))
        # make sure all of A511 command have been executed

    def _usbWrite(self, command):
        if self.debug:
            if len(command) > 3000:
                print("down load firmware")
            else:
                print(command)
        command = command + '\n'

        if self.interface == 'spi' or self.interface == 'i2c':
            self.usb.write(self.out_endpoint_addr, command)
        else:
            cmd = bytes(command, "UTF-8")
            self.socket.send(cmd)

        #time.sleep(0.01)
        read_error = 1
        while read_error > 0:
            read_str = self._usbRead()
            if read_str == None:
                read_error = read_error - 1
                #time.sleep(0.1)
                #print("retry read in _usbWrite")
                continue
            #print("in _usbWrite read_str", read_str)
            r = re.search(r'err', read_str)
            if r != None:
                read_error = read_error - 1
                #time.sleep(0.1)
                #print("retry read in _usbWrite")
                continue
            else:               
                return read_str
        return read_str

    def _usbRead(self):
        if self.interface == 'spi' or self.interface == 'i2c':
            buf = []
            usb_read_retry_cnt = 1
            while usb_read_retry_cnt > 0:
                try:
                    data=""
                # 讀取第一次response (為了讓buf不是空的array)
                    data = self.usb.read(self.in_endpoint_addr,
                                         self.ep_in.wMaxPacketSize)
                    if data == None or len(data) == 0:
                        #print("retry usb read in _usbRead")
                        #time.sleep(0.1)
                        usb_read_retry_cnt = usb_read_retry_cnt - 1
                        continue
                #print("self.ep_in.wMaxPacketSize " , self.ep_in.wMaxPacketSize)
                    break
                except:               
                    #print("retry usb read in _usbRead")
                    #time.sleep(0.1)
                    usb_read_retry_cnt = usb_read_retry_cnt - 1
                    pass
                
            buf.extend(data)
            if len(buf) == 0:
                return None
            # 檢查 response是否結束，以避免以下狀況 :
            # 1_讀取速度太快，其中有幾次讀不到資料造成資料讀取不完整
            # 2_該command會多次返回，例如 identify
            # =====================================
            # 10(0x0a) is end code of usb response,
            # get 10(0x0a) means the response is complete
            while buf[-1] != 10:
                usb_read_retry_cnt = 1
                while usb_read_retry_cnt > 0:
                    try:
                    # 讀取第一次response (為了讓buf不是空的array)
                        data = self.usb.read(self.in_endpoint_addr,
                                             self.ep_in.wMaxPacketSize)
                    #print("self.ep_in.wMaxPacketSize " , self.ep_in.wMaxPacketSize)
                        break
                    except:
                        usb_read_retry_cnt = usb_read_retry_cnt - 1

                buf.extend(data)

            # 把 hex-string 轉成 ascii
            decode_packet = "".join(chr(item) for item in buf)
            if self.debug:
                print(decode_packet.strip())
            return decode_packet
        else:
            result = []
            while True:
               try:
                   result.append(self.socket.recv(4096).decode("UTF-8"))
               except:
                   break
            result = ''.join(result).upper()
            if self.debug:
               print(result)
            return result.__repr__()
            pass

    def autoScanI2CAddr(self):
        addrs = ['50', '20', '2c', '70', '4b', '67', '3c']
        for addr in addrs:
            self.prefix = 'target=0 raw bus-addr={}'.format(addr)
            result = self._usbWrite('{} wr=02'.format(self.prefix))

            check = re.findall("err", result)
            if check == []:
                print('Found I2C device at address 0x{}.'.format(addr))
                self.busAddr = addr
                break

        if self.busAddr == None:
            print("Error : can\'t find I2C Address among {}".format(addrs))
            self.tcmDevice = False
        else:
            print("Found TouchComm device at address: 0x{}.".format(addr))
            self.tcmDevice = True

        self.clearCmd()

    def Config(self):
        if self.interface == 'i2c':
            cmd = 'target=0 config raw pl=i2c pull-ups=yes speed=400'
        elif self.interface == 'spi':
            cmd = 'target=0 config raw pl=spi spiMode={} bitRate={} byteDelay=0 pull-ups=yes ssActive=low mode=slave'.format(
                SPI_MODE, SPI_SPEED)
        else:
            cmd = 'target=0 config raw pl=native attn=none'

        self._usbWrite(cmd)

    def PowerOn(self, vdd=1800, vpu=1800, vled=3300, vddtx=1800):
        self._usbWrite(
            'target=0 power on vdd={} vpu={} vled={} vddtx={}'.format(
                vdd, vpu, vled, vddtx))

    def PowerOff(self):
        self._usbWrite('target=0 power off')

    def DeviceInit(self):
        self.Config()
        if self.interface == 'spi' or self.interface == 'i2c':
            self.PowerOn(vdd=self.voltage['vdd'],
                         vpu=self.voltage['vpu'],
                         vled=self.voltage['vled'],
                         vddtx=self.voltage['vddtx'])

            # wait for power-up
            time.sleep(0.1)
        else:
            #self.getDatabyCmd('02', '01')
            #self.socket.settimeout(0.05)
            pass

        if self.interface == 'i2c' and self.busAddr == None:
            #self.autoScanI2CAddr()
            self.busAddr = '20'

    def printPacket(self, str):
        line_len = 32

        if str == 'A5000000':
            return
        if str == None:
            return
        if len(str) <= 8:
            print(str)
            return
        else:
            data = [int(str[index:index + 2], 16) for index in range(0, len(str), 2)]
            print('Header={}, Length={}'.format(str[0:8], data[2] | data[3] << 8))

        
        data_len = data[2] | data[3] << 8;
        if data_len == 36 * 16 * 2 or data_len == 36 * 18 * 2 or data_len == 34 * 15 * 2:
            if data_len == 36 * 16 * 2:
                rows = 36
                cols = 16
            elif data_len == 36 * 18 * 2:
                rows = 36
                cols = 18
            else:
                rows = 34
                cols = 15
            index = 0
            print('r\c:', end='')
            for col in range(0, cols):
                print('{:4d} '.format(col), end='')
            print("")
            print("")
            for row in range(0,rows):
                print("%2d: " % row, end="")
                for col in range(0, cols):
                    tp_data = (ct.c_int16(data[4 + index] | data[4 + index + 1] << 8)).value
                    index = index + 2
                    print('{:4d} '.format(tp_data), end='')
                print("")
        else:
            print("     ", end="")
            for i in range(0, line_len):
                print('{:02d} '.format(i), end='')

            data = data[4:]
            address = 0
            for index, item in enumerate(data):
                if index % line_len == 0:
                    print('\n{:04d}:'.format(address), end='')
                    address = address + line_len
                print('{:02X} '.format(item), end='')
        print('')

    def sendCmd(self, cmd, needResponse=False, response=None):
        ret = ''
        if cmd != '':
            ret = self._usbWrite('{} {}'.format(self.prefix, cmd))
            if self.interface == "red":
                r = re.search(r'WR COUNT', ret)
                #read out the seq msg
                #seq = self.socket.read(1024)
                
            if needResponse:
                while True:
                    ret = self.getResponse()
                    if response == None:
                        break
                    if ret[2:4] == '00' or ret[2:4] == response:
                        break
                    else:
                        print('Header={}, need self.retry'.format(ret[0:8]))
                        self.retry = self.retry - 1
                        if self.retry:
                            continue
                        else:
                            break
            else:
                #print(ret, type(ret))
                if ret == None:
                    print("no usb response return None")
                    return ret
                r = re.search(r'"A5\S+"', ret)
                if r == None:
                    return None
                else:
                    r = r.group().strip()
                    ret = re.sub('"', '', r)
        self.printPacket(ret)
        return ret
    def sendCmd_cmd_data(self, cmd, data=None):
        ret = ''
        if cmd != '':
            if data == None:
                data_len = 0;
                data_str = ""
            else:
                data_len = len(data) // 2
                data_str = data
            cmd_cdci = 'wr=' + cmd + "%02x%02x" % (data_len % 256, data_len // 256) + data_str
            print(cmd_cdci)
            ret = self._usbWrite('{} {}'.format(self.prefix, cmd_cdci))
        return ret
    def send_raw_data(self, cmd, data=None):
        ret = ''
        if cmd != '':
            if data == None:
                data_len = 0;
                data_str = ""
            else:
                data_len = len(data) // 2
                data_str = data
            cmd_cdci = 'wr=' + cmd  + data_str
            print(cmd_cdci)
            ret = self._usbWrite('{} {}'.format(self.prefix, cmd_cdci))
        return ret

    def readMsg(self):
        str1 = ''
        str2 = ''
        retry_read_msg_cnt = 10
        while retry_read_msg_cnt > 0:
            if "red" == self.interface and False:
                r = self._usbWrite('{} rd=4'.format(self.prefix))
                print(msg)
                return
            else:
            # ===== Get data-length =====
                r = self._usbWrite('{} rd=4'.format(self.prefix))
                #print("read from device r " + r)
                # ===== check and make sure startCode is correct =====
                r = re.search(r'"A5\S+"', r)
                if r == None:
                    #error msg, should read again
                    retry_read_msg_cnt = retry_read_msg_cnt - 1
                    time.sleep(0.1)
                    continue
                    #should read again? no need _usbwrite already do the retry
                    #return None
                else:
                    r = r.group().strip()
                    r = re.sub('"', '', r)
                    if r == 'A5000000':
                        #idle retry read
                        #retry_read_msg_cnt = retry_read_msg_cnt - 1
                        #continue
                        return r
                    break
        str1 = r
        str2 = ''
        length = 3 + int(r[4:6], 16) | int(r[6:], 16) << 8
        if length > 3:
            # ===== Get real data =====
            r = self._usbWrite('{} rd={}'.format(self.prefix, length))
            try:
                # A503 = Continues Read
                data = re.search(r'"A503\S+5A"', r).group().strip()

                # Strip " string at begin and end, then remove A5(startCode)、03(ContinueReadCode)、5A(endCode)
                data = re.sub('"', '', data)[4:-2]
                str2 = data
            except:
                assert False, "ERROR: can't get complete data : {}".format(r)
        return str1 + str2
    def read_msg_bytes(self):
        retry_cnt = 3
        while True:
            response=self.readMsg()
            if response == 'A5000000':
                retry_cnt = retry_cnt - 1
                if retry_cnt:
                    time.sleep(0.1)
                    continue
                else:
                    break
            else:
                break
        response_code = int(response[2:4],16)
        response_data_len = int(response[4:6],16) + int(response[6:8],16) * 256
        response_data = []
        for i in range(response_data_len):
            index = 8 + i * 2
            response_data.append(int(response[index:index+2],16))
        return response_code,response_data_len,response_data

    def write_cmd_and_read_back(self, cmd, data=None, sleep_time=None):
        self.sendCmd_cmd_data(cmd, data)
        if sleep_time == None:
            sleep_time = NORMAL_SLEEP_TIME
        time.sleep(sleep_time)
        retry_cnt = 3
        while True:
            response=self.readMsg()
            if response == 'A5000000':
                retry_cnt = retry_cnt - 1
                if retry_cnt:
                    time.sleep(0.1)
                    continue
                else:
                    break
            else:
                break
        response_code = int(response[2:4],16)
        response_data_len = int(response[4:6],16) + int(response[6:8],16) * 256
        response_data = []
        for i in range(response_data_len):
            index = 8 + i * 2
            response_data.append(int(response[index:index+2],16))
        return response_code,response_data_len,response_data
    def write_cmd_and_read_back_check(self, cmd, data=None, sleep_time=None):
        response_code,response_data_len,response_data = self.write_cmd_and_read_back(cmd,data,sleep_time)
        if (response_code == 1) or (response_code == 0):
            return True
        return False
    def getResponse(self):
        while True:
            r = self.readMsg()
            if r == 'A5000000':
                self.retry = self.retry - 1
                if self.retry:
                    time.sleep(0.01)
                    continue
                else:
                    break
            elif r == None:
                continue
            else:
                break
        return r
    def getDeviceMode(self):
        code,len_bytes,data=self.write_cmd_and_read_back('02')
        if code == 0x01 and data[1] == 0x01:
            return "app"
        if code == 0x01 and data[1] == 0x0c:
            return "bl"
        return "unknown" 
    def getDatabyCmd(self, cmdCode, statusCode):
        msg = 'A5{}'.format(statusCode)
        retry = 10
        self._usbWrite('{} wr={}0000'.format(self.prefix, cmdCode))
        while True:
            time.sleep(0.01)
            r = self.readMsg()
            if r == 'A5000000':
                time.sleep(0.01)
                retry = retry - 1
                if (retry == 0):
                    return None
                continue
            elif r == None:
                continue
            elif msg == r[0:4]:
                break
        #print(r)
        r = r[8:]
        data = [int(r[index:index + 2], 16) for index in range(0, len(r), 2)]
        return data
    def writeLongCmd(self, cmd, write_data, data_len):
            #print(type(write_data),data_len)
            write_chunk_size = 256
            remaining_size = data_len
            offset = 0
            write_cmd_cnt = 0
            first_send = True
            data_str = write_data
            while remaining_size > 0:
                if remaining_size > 256:
                    data_size = write_chunk_size
                else:
                    data_size = remaining_size
                
                if first_send == True:
                    cmd_code = cmd
                    data_size = 254
                    first_send = False
                    send_cmd_str = "%02x" % int(data_len % 256) + "%02x" % int(data_len // 256) + data_str[offset*2:offset*2 + data_size*2]
                else:
                    cmd_code = "01"
                    send_cmd_str = data_str[offset*2:offset*2 + data_size*2]
                remaining_size = remaining_size - data_size
                offset = offset + data_size
                #print(flash_cmd_str)
                #code, length, data=self.write_cmd_and_read_back("12", flash_cmd_str, 0.1)
                write_cmd_cnt = write_cmd_cnt + 1
                self.send_raw_data(cmd_code, send_cmd_str)
            print("send long cmd done, about to read")
            time.sleep(0.2)
            self.readMsg()
    def download_config(self, config_type, config_data, config_len):
        version_str = "01"
        config_data_str = ""
        if config_type == "app":
            config_type_str = "01"
            if (config_len < 4096):
                for i in range(config_len, 4096):
                    config_data.append(0)
            config_len = 4096
        elif config_type == "disp":
            config_type_str = "02"
        for i in range(0, config_len):
            config_data_str = config_data_str + "%02x" % config_data[i]
        raw_data = version_str + config_type_str + config_data_str
        self.writeLongCmd("30", raw_data, len(raw_data) // 2)
    def writeFlash(self, flash_addr, flash_data, flash_data_size):
        write_chunk_size = 512
        block_size = 8
        remaining_size = flash_data_size
        offset = 0
        write_cmd_cnt = 0
        data_str = ""
        a = True
        block_addr_low = 0
        block_addr_high = 0
        while remaining_size > 0:
            if remaining_size > 512:
                data_size = write_chunk_size
            else:
                data_size = remaining_size
            remaining_size = remaining_size - data_size
            block_addr = int((flash_addr + offset) / block_size)
            block_addr_low = int(block_addr % 256)
            block_addr_high = int(block_addr / 256)
            data_str = ""
            for i in range(0,data_size):
                data_str += "%02x" % flash_data[offset + i]
            flash_write_cmd_data= "%02x" % block_addr_low + "%02x" % block_addr_high + data_str
            #flash_write_cmd_data_len = data_size + 2
            flash_cmd_str = flash_write_cmd_data
            offset = offset + data_size
            #print(flash_cmd_str)
            code, length, data=self.write_cmd_and_read_back("12", flash_cmd_str, 0.1)
            write_cmd_cnt = write_cmd_cnt + 1
            if code != 0x01:
                print("write flash fail", write_cmd_cnt, offset, data_size, block_addr_high, block_addr_low)
                return False
        #print(write_cmd_cnt)
        return True
    def getStaticCfg(self):
        return self.getDatabyCmd(cmdCode='21', statusCode='01')
    def update_firmware(self):
        app_address = 0
        app_data = ""
        app_length = 0
        app_config_address = 0
        app_config_data = ""
        app_config_length = 0
        disp_address = 0
        disp_data = ""
        disp_length = 0
        global img_file_path
        if img_file_path == None:
            print("img file path", img_file_path)
            print("no img file path, return")
            return
        img = TouchBootImageFile.load(img_file_path) 
        for i in range(len(img.flashAreas)):
            if (img.flashAreas[i]['name'] == 'APP_CODE'):
                app_address = img.flashAreas[i]['address']
                app_data = img.flashAreas[i]['data']
                app_length = img.flashAreas[i]['length']                
                #print(app_address, app_data, app_length)
            if (img.flashAreas[i]['name'] == 'APP_CONFIG'):           
                app_config_address = img.flashAreas[i]['address']
                app_config_data = img.flashAreas[i]['data']
                app_config_length = img.flashAreas[i]['length']                
                #print(app_config_address, app_config_data, app_config_length)
            if (img.flashAreas[i]['name'] == 'DISPLAY'):           
                disp_address = img.flashAreas[i]['address']
                disp_data = img.flashAreas[i]['data']
                disp_length = img.flashAreas[i]['length']
        page_size = 2048 * 2
        write_block_size = 4 * 2
        app_start_page = int(app_address * 2 / page_size)
        app_page_cnt = int((app_length / page_size))
        if (app_length  % page_size):
            app_page_cnt = app_page_cnt + 1
        app_config_start_page = int(app_config_address * 2 / page_size)
        app_config_page_cnt = int((app_config_length / page_size))
        if (app_config_length % page_size):
            app_config_page_cnt = app_config_page_cnt + 1
        disp_config_start_page = int(disp_address * 2 / page_size)
        disp_config_page_cnt = int((disp_length / page_size))
        if (disp_length  % page_size):
            disp_config_page_cnt = disp_config_page_cnt + 1
        print(app_start_page, app_page_cnt,app_config_start_page,app_config_page_cnt,disp_config_start_page,disp_config_page_cnt)
        #erase app
        
        erase_cmd_data_str = '%02x%02x' % (app_start_page, app_page_cnt)
        print(erase_cmd_data_str)        
        if self.write_cmd_and_read_back_check('11',erase_cmd_data_str, 8):
            print("erase app OK")
            if self.writeFlash(app_address * 2, app_data, app_length):
                print("update app OK")
            else:            
                print("update app fail")
                return
        else:
            print("erase app fail")
            return
            #print("erase app OK")
        
        erase_cmd_data_str = '%02x%02x' % (app_config_start_page, app_config_page_cnt)
        print(erase_cmd_data_str)        
        if self.write_cmd_and_read_back_check('11',erase_cmd_data_str, 1):
            print("erase app config OK")
            if self.writeFlash(app_config_address * 2, app_config_data, app_config_length):
                print("update app config OK")
            else:            
                print("update app config fail")
                return
        else:
            print("erase app config fail")
            return

        erase_cmd_data_str = '%02x%02x' % (disp_config_start_page, disp_config_page_cnt)
        print(erase_cmd_data_str)        
        if self.write_cmd_and_read_back_check('11',erase_cmd_data_str, 1):
            print("erase app config OK")
            if self.writeFlash(disp_address * 2, disp_data, disp_length):
                print("update disp config OK")
            else:            
                print("update disp config fail")
                return
        else:
            print("erase disp config fail")
            return
        print("update firmware OK!!!!!!!!!!!!!!!!")
        print("about to switch to app firmware")
        app_bl_mode = self.getDeviceMode()
        if "ap" == app_bl_mode:
            print("switch to app firmware ok")
        elif "bl" == app_bl_mode:
            response_code,response_data_len,response_data = self.write_cmd_and_read_back("14")
            if response_code == 0x10 and response_data[1] == 0x01 or response_code == 0x0:
                print("switch to app firmware ok")
    def clearCmd(self):
        while True:
            r = self._usbWrite('{} rd=4'.format(self.prefix))
            if self.debug:
                print(r)
            status = re.search('"A5000000"', r)
            if status == None:
                pass
            else:
                break

    def Quit(self):
        if self.interface == 'i2c' or self.interface == 'spi':
            #self.PowerOff()
            if self.usb is not None:
                usb.util.dispose_resources(self.usb)
            self.connected = False
        else:
            #self.socket.close()
            pass


def main(argv):
    i2c_addr = '50'
    last_str = ""
    str = ""
    global img_file_path
    print("len of argv", len(argv))
    if len(argv) == 1:
        interface = 'spi'
    else:
        if argv[1].lower() == 'i2c':
            interface = 'i2c'
        elif argv[1].lower() == 'spi':
            interface = 'spi'
        else:
            interface = 'red'
            subprocess.getstatusoutput("~/bin/start-red-remote.sh")
            time.sleep(1.5)
    if len(argv) >= 3:
        i2c_addr = argv[2]
        
    if len(argv) >= 4:
        img_file_path = argv[3]
        print("img_file_path is", img_file_path)
    if len(argv) >= 5:
        lst_file_path = argv[4]
        print("lst_file_path is", lst_file_path)
    cm2 = Comm2(ip=interface, busAddr=i2c_addr, vddh=VDDH_VOLTAGE, vddio=VDDIO_VOLTAGE, debug=True)

    if cm2.connected == False:
        return

    if cm2.tcmDevice == False:
        print("TouchComm device is not connected!")
        cm2.Quit()
        return

    #cm2.printPacket(cm2.readMsg())

    #raw = cm2.getDatabyCmd(cmdCode='02', statusCode='01')
    #B1 = raw[18]
    #B2 = raw[19]
    #B3 = raw[20]
    #B4 = raw[21]
    #packrat = B4 << 24 | B3 << 16 | B2 << 8 | B1
    #print('Packrat={}'.format(packrat))
    
    while True:
        if str == "repeat":
            #print("repeart here", last_valid_str, str, last_str)
            str = last_str
            print("repeart last cmd", last_str)
        else:
            str = input("Input cmd here:")          
            if str == "l":
                #print("input here", last_valid_str, str, last_str)
                str = "repeat"
                continue
        if str:
            last_valid_str = str
            last_str = last_valid_str 
            if str == "usbr":
                cm2._usbRead()
                continue
            if str == "hdl":            
                if img_file_path == None:
                    print("no img file path, return")
                f35_img_file = TouchBootImageFile.load(img_file_path) 
                f35_app_code = f35_img_file.flashAreas[1]["data"]  #1 should be app
                app_code_len = len(f35_app_code)
                retry = 10
                while (True):
                    hdl_request=cm2._usbWrite("target=0 raw wr=8000 rd=1\n")
                    retry = retry - 1
                    if hdl_request == None:
                        continue
                    r = re.search(r'data="\S+"', hdl_request).group().strip()
                    if r == None and retry > 0:
                        continue
                    break
                print("hdl_request is", hdl_request)
                r = re.search(r'data="\S+"', hdl_request).group().strip()
                if r != 'data="4B"':
                    print("not request fw, return")
                    continue
                cm2._usbRead()
                cm2._usbRead()
                if True:
                    cm2._usbWrite("target=0 raw wr=001804")
                    download_str="target=0 raw wr=001c download at=0 size=%d\n" % app_code_len
                    cm2._usbWrite(download_str)
                    print("f35_app_code size", app_code_len)
                    f35_app_code_str = ""
                    for i in range(0, len(f35_app_code)):
                        f35_app_code_str = f35_app_code_str + "%02x" % f35_app_code[i]
                    f35_app_code_str = f35_app_code_str + "\n"
                    send_str="wr=001c" + f35_app_code_str
                    cm2.sendCmd(send_str.strip())
                    time.sleep(0.3)
                    cm2._usbRead()
                    cm2._usbRead()
                else:
                    f35_app_code_str = ""
                    for i in range(0, len(f35_app_code)):
                        f35_app_code_str = f35_app_code_str + "%02x" % f35_app_code[i]
                    cmd_str = "target=0 hdl crc at=0 size=%d" % app_code_len
                    cm2._usbWrite(cmd_str)
                    remain = app_code_len % 512
                    if remain == 0:
                        remain = 512
                        indexs = app_code_len // 512
                    else:
                        indexs = app_code_len // 512 + 1
                    for i in range(0, indexs):
                        str_index = i * 512
                        data_size = 512
                        if i == indexs - 1:
                            data_size = remain
                        cmd_str = "target=0 hdl send idx=%d data="%i + f35_app_code_str[str_index*2 :str_index*2 + data_size * 2]
                        cm2._usbWrite(cmd_str)
                    cm2._usbWrite("target=0 config raw pl=spi pull-ups=yes spiMode=3 byteDelay=10 bitRate=500 attn=none ssActive=low mode=slave base64=yes")
                    cm2._usbRead()
                    cm2._usbWrite("target=0 asic reset level=low output=open-drain time=1000")
                    cm2._usbRead()
                    cm2._usbWrite("target=0 raw wr=001804")
                    cm2._usbRead()
                    cmd_str = "target=0 raw wr=001c download at=0 size=%d" % app_code_len
                    cm2._usbWrite(cmd_str)
                    cm2._usbRead()
                    cm2._usbRead()
                    time.sleep(0.2)
                    #cm2._usbWrite("target=0 raw rd=4")
                    
                response_code,response_data_len,response_data = cm2.read_msg_bytes()
                if (response_code == 0x10):
                    print("download app ok")
                    response_code,response_data_len,response_data = cm2.read_msg_bytes()
                    if (response_code == 0x1b):
                        print("need to download app_config display_config", response_data[0] & 0x04, response_data[0] & 0x02)
                        if (response_data[0] & 0x04 == 0x04):
                            print("download app config")
                            app_config_data = f35_img_file.flashAreas[2]["data"]  #2 should be app config
                            #data_str = "0101"
                            #for i in range(0, len(app_config_data)):
                                #data_str = data_str + "%02x" % app_config_data[i]
                            #raw_data_size = len(app_config_data) + 2
                            #data_str = "%02x%02x" % (int(raw_data_size % 256), int(raw_data_size // 256)) + data_str
                            #data_str = "%02x%02x" % (int(raw_data_size % 256), int(raw_data_size // 256)) + "data_str"

                            cm2.download_config("app", app_config_data, len(app_config_data))
                        if (response_data[0] & 0x02 == 0x02):
                            print("download disp")
                            display_data = f35_img_file.flashAreas[3]["data"]    #3 should be display config
                            cm2.download_config("disp", display_data, len(display_data))

                        if "app" == cm2.getDeviceMode():                                            
                            print("host download success")
                            #print("fw information is \n",f35_img_file.flashAreas[1]["name"], f35_img_file.flashAreas[1]["length"], f35_img_file.flashAreas[1]["crc"])                            
                            raw = cm2.getDatabyCmd(cmdCode='02', statusCode='01')
                            B1 = raw[18]
                            B2 = raw[19]
                            B3 = raw[20]
                            B4 = raw[21]
                            packrat = B4 << 24 | B3 << 16 | B2 << 8 | B1
                            print('Packrat={}'.format(packrat))
                            print("fw information is \n",f35_img_file.flashAreas[1]["name"], f35_img_file.flashAreas[1]["length"], f35_img_file.flashAreas[1]["crc"])
                            print("fw information is \n",f35_img_file.flashAreas[2]["name"], f35_img_file.flashAreas[2]["length"], f35_img_file.flashAreas[2]["crc"])
                            print("fw information is \n",f35_img_file.flashAreas[3]["name"], f35_img_file.flashAreas[3]["length"], f35_img_file.flashAreas[3]["crc"])
                continue

            if str == "up":            
                #print(img.flashAreas[0]["data"][1])
                device_mode = cm2.getDeviceMode()
                if device_mode == "app":
                    code,len_bytes,data=cm2.write_cmd_and_read_back('1f')
                    if code != 0x10:
                        print("enter bl NG")
                        continue
                    if data[1] == 0xc:
                        print("enter bl OK")
                    else:
                        print("enter bl NG")
                if device_mode == "unknown":
                    continue
                
                code,len_bytes,data = cm2.write_cmd_and_read_back('11','0808', 1)
                if code == 0x01:
                    print("erase ok")
                else:
                    print("erase NG")
                    continue
                cm2.update_firmware()
                continue
            if str == "er":
                device_mode = cm2.getDeviceMode()
                if device_mode == "app":
                    code,len_bytes,data=cm2.write_cmd_and_read_back('1f')
                    if code != 0x10:
                        print("enter bl NG")
                        continue
                    if data[1] == 0xc:
                        print("enter bl OK")
                    else:
                        print("enter bl NG")
                if device_mode == "unknown":
                    continue
                
                code,len_bytes,data = cm2.write_cmd_and_read_back('11','0808', 2)
                if code == 0x01:
                    print("erase ok")
                else:
                    print("erase NG")
                continue
            str = str.replace(" ", "")
            if '=' in str:
                cmds = str.split('=')
                cmd = cmds[0]
                data = cmds[1]
                if cmd == 'rd' or cmd == 'r':
                    cm2.sendCmd('rd=' + cmds[1])
                else:
                    if len(data) < 3:
                        str = 'wr=' + data + '0000'
                    else:
                        id = data[0:2]
                        data = data[2:]
                        size = len(data) // 2
                        str = 'wr={}{:02X}{:02X}{}'.format(id, size % 256, size // 256, data)
                    print(str)

                    if cmd == 'cmd':
                        cm2.sendCmd(str.strip(), True, '01')
                    elif cmd == 'wr':
                        cm2.sendCmd(str.strip(), True)
                    elif cmd == 'wrnr':
                        cm2.sendCmd(str.strip())
            elif str=='i':               
                raw = cm2.getDatabyCmd(cmdCode='02', statusCode='01')
                if None == raw:
                    continue
                B1 = raw[18]
                B2 = raw[19]
                B3 = raw[20]
                B4 = raw[21]
                packrat = B4 << 24 | B3 << 16 | B2 << 8 | B1
                print('Packrat={}'.format(packrat))
            elif str=='r':               
                cm2.printPacket(cm2.readMsg())
            elif str=='kr':
                cnt = 200
                while cnt > 0:               
                    cm2.printPacket(cm2.readMsg())
                    cnt = cnt -1
                    time.sleep(0.2)
            elif str=='gr':
                cm2.write_cmd_and_read_back('05','13')
                cnt = 10
                while cnt > 0:               
                    cm2.printPacket(cm2.readMsg())
                    cnt = cnt -1
                    time.sleep(0.2)
                cm2.write_cmd_and_read_back('06','13')    
            elif str=='gd':
                cm2.write_cmd_and_read_back('05','12')
                cnt = 10
                while cnt > 0:               
                    cm2.printPacket(cm2.readMsg())
                    cnt = cnt -1
                    time.sleep(0.2)
                cm2.write_cmd_and_read_back('06','12')  
            elif str[0]=='p':
                #print("print variable here")
                if lst_file_path == None:
                    print("you need to set the lst symbol name file path, please enter")
                    lst_file_path = input("path of the lst file:")
                name = str.split('#')
                print(name)
                if len(name) == 2:
                    p_string = name[1]
                else:
                    continue
                if p_string == "fw-status":
                    addr_str = "70ff"
                    length_str = "1000"
                    cmd_data_str =  addr_str + length_str
                    #cm2.sendCmd(ram_cmd, True, '01')
                    response_code,response_data_len,response_data = cm2.write_cmd_and_read_back("81",cmd_data_str, 1)
                    if (response_code == 0x01):
                        #print(response_data)
                        for i in range(0, 8):
                            print("TPC%dA :0x%x"%(i,(response_data[i*2] | response_data[i*2 + 1] << 8)))
                            #print("TPC%dB :0x%x"%(i,(response_data[16 + i*2] | response_data[16 + i*2 + 1] << 8)))
                        
                    continue
                cmd = "grep -irn %s  %s | grep -i %s=reg | awk '{print $2}'" % (p_string,lst_file_path, p_string)
                cmd2 = "grep -irn  %s  %s  | grep WORD | wc -l" % (p_string,lst_file_path)
                print(cmd)
                retcode, output = subprocess.getstatusoutput(cmd)
                retcode2, output2 = subprocess.getstatusoutput(cmd2)
                if (retcode == 0):
                    print(output)
                    output = output.strip("$")
                    print(output)
                    addr_str = ""
                    length_str = ""
                    if len(output) <=2:
                        addr_str = output[0:2] + '00'                        
                    else:                    
                        addr_str = output[2:] + output[0:2]
                    if int(output2) > 256:
                        length_str = "%02x" % (int(output2) % 256) + "%02x" % (int(output2) // 256)
                    else:                    
                        length_str = "%02x" % (int(output2) % 256) + "00"
                    ram_cmd = 'wr=810400' + addr_str + length_str

                    cmd_data_str = addr_str + length_str
                    print(ram_cmd)
                    cm2.sendCmd(ram_cmd, True, '01')
                    continue

                    response_code,response_data_len,response_data = cm2.write_cmd_and_read_back("81",cmd_data_str, 1)
                    if (response_code == 0x01) and response_data_len >= 16 * 36:
                        index = 0
                        out_range = False
                        for t in range(0,tx_cnt):
                            row_data = ""
                            if out_range == True:
                                continue
                            for r in range(0, rx_cnt):
                                if index + 1 >= response_data_len:
                                    out_range = True
                                    continue
                                row_data = row_data + "%04x, " % (response_data[index] + response_data[index + 1] * 256)
                                index = index + 2
                            print("row at %d" % t, row_data)
                else:
                    continue
            else:
                if str == 'q' or str == 'quit':
                    break
                elif str == 'run123456': # disable this feature since not working yet
                    cnt = 0
                    while True:
                        cm2.printPacket(cm2.readMsg())
                        time.sleep(0.003)
                        cnt = cnt + 1
                        #if msvcrt.kbhit():
                        #  msvcrt.getch()
                        #  break
                elif str == 'check':                
                    cm2.printPacket(cm2.readMsg())
                elif str == 'rmi4':
                    cm2.rmi_mode = True
                elif str == 'comm2':
                    cm2.rmi_mode = False
                else:
                    id=str[0:2]
                    if (cm2.rmi_mode == True):
                        str = 'wr={}'.format(str)
                    else:
                        if len(str) >= 3:
                            data = str[2:]
                            size = len(data) // 2
                            try:
                                str = 'wr={}{:02X}{:02X}{}'.format(id, size % 256, size // 256, data)
                            except:
                                continue
                        else:
                            str = 'wr=' + id + '0000'   #comm2
                    cm2.sendCmd(str.strip())
    cm2.Quit()

if __name__ == '__main__':
    USAGE = '''
Released on Dec.5, 2019, by Rover Shen.
This is a tool for cdci console replacement when using MPC04 to connect with TouchComm module.
You need to install filter driver over MPC04 USB devices provided by LibUSB-Win32 toolkit before using it.
LibUSB-Win32 can be downloaded here:
https://sourceforge.net/projects/libusb-win32/
Example:
cmd=05c0  #enable c0 report and read until $01(OK) response is received
rd=1200   #read 1200 bytes from interface
wr=1f     #enter bootloader and read a response
wrnr=04   #software reset without reading anything
check     #try to read a packet
run       #keep reading packet, any key to stop
quit      #quit the script
'''
    print(USAGE)
    main(sys.argv)
