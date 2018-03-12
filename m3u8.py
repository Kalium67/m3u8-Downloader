#coding: utf-8
from sys import argv
from gevent import monkey
monkey.patch_all()
from gevent.pool import Pool
import gevent
import requests
import urlparse
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
            body = r.content
            if body:
                ts_list = [urlparse.urljoin(m3u8_url, n.strip()) for n in body.split('\n') if n and not n.startswith("#")]
                if not (start_file or end_file==0):
                    ts_time = [float(n[8:-1]) for n in body.split('\n') if n and n.startswith("#EXTINF:")]
                    i = 0
                    for index in range(len(ts_time)):
                        i += ts_time[index]
                        if i <= start_time:
                            start_file=index+1
                        if i >= end_time and end_time != -1:
                            end_file=index
                            break
                    if not end_file:
                        end_file=len(ts_time)
                    print "[Start File]:\t",start_file
                    print "[End File]:\t",end_file
                ts_list = ts_list[start_file:end_file]
                ts_list = zip(ts_list, [n for n in xrange(len(ts_list))])
                if ts_list:
                    self.ts_total = len(ts_list)
                    print 'Total files:'+bytes(self.ts_total)
                    g1 = gevent.spawn(self._join_file)
                    self._download(ts_list)
                    g1.join()
        else:
            print r.status_code

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
                    print file_name+'\t|\t'+r.headers['content-length']+'B'+'\t|\t'+bytes(self.ts_finish)+'/'+bytes(self.ts_total)
                    with open(os.path.join(self.dir, file_name), 'wb') as f:
                        f.write(r.content)
                    self.succed[index] = file_name
                    return
            except:
                retry -= 1
        print '[Fail]%s' % url
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
        print argv[3:]
        opts, args = getopt.getopt(argv[3:],"ht:s:e:f:g:")
        print opts
    except getopt.GetoptError:
        print 'm3u8.py -s <start_time> -e <end_time>'
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print 'm3u8.py -s <start_time> -e <end_time>'
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
    print "[Downloading]:", cm3u8url
    print "[Save Path]:", cpath
    if starttime: print "[Start Time]:", starttime
    if endtime: print "[End Time]:", endtime
    if startfile: print "[Start File]:", startfile
    if endfile: print "[End File]:", endfile

    downloader = Downloader(cthread)
    downloader.run(cm3u8url, cpath, starttime, endtime, startfile, endfile)
