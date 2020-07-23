sudo echo “qyh ALL=NOPASSWD:ALL”  >> /etc/sudoers
cat <<EOF > tmp.list
deb http://mirrors.aliyun.com/ubuntu/ xenial main
deb-src http://mirrors.aliyun.com/ubuntu/ xenial main
deb http://mirrors.aliyun.com/ubuntu/ xenial-updates main
deb-src http://mirrors.aliyun.com/ubuntu/ xenial-updates main
deb http://mirrors.aliyun.com/ubuntu/ xenial universe
deb-src http://mirrors.aliyun.com/ubuntu/ xenial universe
deb http://mirrors.aliyun.com/ubuntu/ xenial-updates universe
deb-src http://mirrors.aliyun.com/ubuntu/ xenial-updates universe
deb http://mirrors.aliyun.com/ubuntu/ xenial-security main
deb-src http://mirrors.aliyun.com/ubuntu/ xenial-security main
deb http://mirrors.aliyun.com/ubuntu/ xenial-security universe
deb-src http://mirrors.aliyun.com/ubuntu/ xenial-security universe
EOF

cat /etc/apt/sources.list >> tmp.list
sudo cp ./tmp.list /etc/apt/sources.list
rm tmp.list

sudo apt-get update

#here should set the ~/bin to path, because we use the install.sh

install.sh vim vim-gnome redshift

install.sh python2.7-dev
install.sh mutt
sudo apt-get install -f -y
sudo apt install git gitk -y
git config --global user.name "yuehao.qiu"
git config --global user.email "scutqyh@163.com"
git config --global diff.tool "meld"
sudo apt install meld -y

cd ~;
git clone https://github.com/qiuyuehao/vim_config;
cd vim_config;
git checkout config_folder;

sudo apt install redshift-gtk -y
sudo apt install terminator -y
cp ~/vim_config/.config/* ~/.config/ -rf



