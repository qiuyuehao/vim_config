#install deep-in windows
cd ~;
git clone https://gitee.com/wszqkzqk/deepin-wine-for-ubuntu.git;
cd deepin-wine-for-ubuntu;
./install_2.8.22.sh
cd ~/Downloads
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.com.wechat/deepin.com.wechat_2.6.8.65deepin0_i386.deb
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.com.qq.im/deepin.com.qq.im_9.1.8deepin0_i386.deb
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.com.foxmail/deepin.com.foxmail_7.2deepin3_i386.deb
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.com.baidu.pan/deepin.com.baidu.pan_5.7.3deepin0_i386.deb
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.cn.com.winrar/deepin.cn.com.winrar_5.3.0deepin2_i386.deb
wget https://mirrors.aliyun.com/deepin/pool/non-free/d/deepin.com.thunderspeed/deepin.com.thunderspeed_7.10.35.366deepin18_i386.deb


sudo dpkg -i deepin*
sudo apt-get install -f -y
sudo dpkg -i deepin*
