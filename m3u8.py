#coding: utf-8
from sys import argv
from gevent import monkey
monkey.patch_all()
from gevent.pool import Pool
import gevent
import requests
from urllib.parse import urljoin
import os
import time
import getopt

class Downloader:
    def __init__(self, pool_size, retry=3):
        self.pool = Pool(pool_size)
        self.session = self._get_http_session(pool_size, pool_size, retry)
        self.retry = retry
        self.dir = ''
        self.succed = {}
        self.failed = []
        self.ts_total = 0
        self.ts_finish = 0

    def _get_http_session(self, pool_connections, pool_maxsize, max_retries):
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=pool_connections, pool_maxsize=pool_maxsize, max_retries=max_retries)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            return session

    def run(self, m3u8_url, dir='', start_time=0, end_time=-1, start_file=0, end_file=0):
        self.dir = dir
        if self.dir and not os.path.isdir(self.dir):
            os.makedirs(self.dir)
        r = self.session.get(m3u8_url, timeout=10)
        if r.ok:
            # python3需要使用decode()把获取到的内容bytes r.content转换为str body 
            body = r.content.decode()
            if body:
                # 把每一行不以'#'开头的m3u8源文件加入ts_list中
                ts_list = [urljoin(m3u8_url, n.strip()) for n in body.split('\n') if n and not n.startswith("#")]

                # 如果start_file和end_file不存在，则使用start_time和end_time来决定。
                if not (start_file or end_file):
                    # 如果start_time不存在，则默认为0
                    if not (start_time):
                        start_time=0
                    # 提取body中'#EXTINF:1234.56,'行中的浮点数，从':'后到','前，作为ts_list对应的ts_time
                    ts_time = [float(n[8:-1]) for n in body.split('\n') if n and n.startswith("#EXTINF:")]
                    i = 0
                    start_file = 0
                    # 对ts_time依次：
                    # 图解'['开始，']'结束，===文件，数字-索引：0======.1===[====.2======.3======.4====]====.5=======
                    # 应从1开始下载，到4结束。
                    for index in range(len(ts_time)):
                        # 计算增加此文件后总时长
                        i += ts_time[index]
                        # 如果增加后小于等于开始时长，那么应该从下一个文件开始，即index+1。
                        # {0======}.1===[====.2======.3======.4====]====.5=======
                        # 加了0文件时长后{}内时长小于等于开始时长'['，应从1开始，加了1后不会再触发此条件。
                        if i <= start_time:
                            start_file=index+1
                        # 如果增加后大于等于结束时长，且结束不为-1，那么应该从当前文件结束，即index。
                        # {0======.1===[====.2======.3======.4====]====}.5=======
                        # 加了4文件时长后{}内时长大于等于结束时长']'，应从4结束，但实际索引从5结束，即下载1[]5之间内容。
                        # 实际下载内容：0======.1 { ===[====.2======.3======.4====]====. } 5=======
                        if i >= end_time and end_time != -1:
                            end_file=index+1
                            break
                        # 显示start_file和end_file
                    print ("[Start File]:\t",start_file)
                    print ("[End File]:\t",end_file)
                # 没有设置end_file默认最后结束
                if not end_file:
                    end_file=len(ts_time)
                ts_list = ts_list[start_file:end_file]
                ts_list = list(zip(ts_list, [n for n in range(len(ts_list))]))
                if ts_list:
                    self.ts_total = len(ts_list)
                    print ('[Total files]:'+str(self.ts_total))
                    g1 = gevent.spawn(self._join_file)
                    self._download(ts_list)
                    g1.join()
        else:
            print (r.status_code)

    def _download(self, ts_list):
        self.pool.map(self._worker, ts_list)
        if self.failed:
            ts_list = self.failed
            self.failed = []
            self._download(ts_list)

    def _worker(self, ts_tuple):
        url = ts_tuple[0]
        index = ts_tuple[1]
        retry = self.retry
        while retry:
            try:
                r = self.session.get(url, timeout=20)
                if r.ok:
                    file_name = url.split('/')[-1].split('?')[0]
                    self.ts_finish += 1
                    print (file_name+'\t|\t'+r.headers['content-length']+'B'+'\t|\t'+str(self.ts_finish)+'/'+str(self.ts_total))
                    with open(os.path.join(self.dir, file_name), 'wb') as f:
                        f.write(r.content)
                    self.succed[index] = file_name
                    return
            except:
                retry -= 1
        print ('[Fail]%s' % url)
        self.failed.append((url, index))

    def _join_file(self):
        index = 0
        outfile = ''
        while index < self.ts_total:
            file_name = self.succed.get(index, '')
            if file_name:
                infile = open(os.path.join(self.dir, file_name), 'rb')
                if not outfile:
                    outfile = open(os.path.join(self.dir, file_name.split('.')[0]+'_all.'+file_name.split('.')[-1]), 'wb')
                outfile.write(infile.read())
                infile.close()
                os.remove(os.path.join(self.dir, file_name))
                index += 1
            else:
                time.sleep(1)
        if outfile:
            outfile.close()

if __name__ == '__main__':
    cthread = 25
    cm3u8url = argv[1]
    cpath = argv[2]
    cpath = cpath.replace("\\","\\\\")
    starttime=None
    endtime=None
    startfile=None
    endfile=None
    try:
        # print (argv[3:])
        opts, args = getopt.getopt(argv[3:],"ht:s:e:f:g:")
        # print (opts)
    except getopt.GetoptError:
        print ('m3u8.py -s <start_time> -e <end_time>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print ('m3u8.py -s <start_time> -e <end_time>')
            sys.exit()
        elif opt in ("-t", "--thread"):
            cthread = arg
        elif opt in ("-s", "--starttime"):
            starttime = float(arg)
        elif opt in ("-e", "--endtime"):
            endtime = float(arg)
        elif opt in ("-f", "--startfile"):
            startfile = int(arg)
        elif opt in ("-g", "--endfile"):
            endfile = int(arg)
    print ("[Downloading]:", cm3u8url)
    print ("[Save Path]:", cpath)
    if starttime: print ("[Start Time]:", starttime)
    if endtime: print ("[End Time]:", endtime)
    if startfile: print ("[Start File]:", startfile)
    if endfile: print ("[End File]:", endfile)

    downloader = Downloader(cthread)
    downloader.run(cm3u8url, cpath, starttime, endtime, startfile, endfile)
