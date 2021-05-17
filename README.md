# zksync-auto

# Install
# Step 1: install zksync-python
git clone https://github.com/zksync-sdk/zksync-python.git
cd zksync-python
pipenv install --python 3.8
pipenv shell
pipenv install python-dot
pipenv install -e .
# Step 1.1: setup crypto library
wget -c https://github.com/zksync-sdk/zksync-crypto-c/releases/download/v0.1.0/zks-crypto-linux-x64.a
wget -c https://github.com/zksync-sdk/zksync-crypto-c/releases/download/v0.1.0/zks-crypto-linux-x64.so
touch .env
ZK_SYNC_LIBRARY_PATH=./zks-crypto-linux-x64.so

# Step 2: GLIBC_2.18 not found 	ref -> https://www.jianshu.com/p/513e01fbd3e0
strings /lib64/libc.so.6 |grep GLIBC_2.18
wget http://mirrors.ustc.edu.cn/gnu/libc/glibc-2.18.tar.gz
tar -zxvf glibc-2.18.tar.gz
cd glibc-2.18
mkdir build
cd build
../configure --prefix=/usr
make -j4
sudo make install

# Others
# DB status
db status:
0	created without funds
1	funds without actived
2	actived with extra eth
3	already transfer extra eth to main wallet
4	airdrop already transfer to main wallet
5	already transfer all eth to main wallet

# .env sample
ZK_SYNC_LIBRARY_PATH=./zks-crypto-linux-x64.so
AIRDROP=FALSE
MAIN_PRIKEY=0x0000000000000000000000000000000000000000000000000000000000000000
