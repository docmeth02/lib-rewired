#       0 File
#       1 Directory
#       2 Uploads Directory
#       3 Drop Box Directory
import threading
import ssl
import time
import os
import hashlib
import socket as pysocket
from rewiredsocket import makeconn
from os import path, mkdir, walk
from shutil import move


class wiredfile():
    def __init__(self, parent, data=False):
        self.parent = parent
        self.logger = self.parent.logger
        self.transferParent = 0
        self.path = ""
        self.type = 0
        self.size = 0
        self.created = 0
        self.modified = 0
        self.checksum = 0
        self.comment = 0

        if data:  # init from directroy listing
            try:
                self.path = data[0]
                self.type = data[1]
                self.size = data[2]
                self.created = data[3]
                self.modified = data[4]
            except (KeyError, IndexError) as e:
                self.logger.error("wiredfile: failed to init from supplied dataset: %s", e)

    def stat(self):
        if not self.path:
            return 0
        msg = "STAT %s" % self.path
        if not self.parent.socketthread.send(msg):
            self.logger.error("stat: failed to send msg to server")
            return 0
        data = self.parent.getMsg(402, 1)
        if not data:
            self.logger.error("stat: request for %s timed out", self.path)
            return 0
        data = data.msg
        if not data[0] == self.path:
            self.logger.error("stat: requested info for %s got %s!", self.path, data[0])
        try:
            self.type = data[1]
            self.size = data[2]
            self.created = data[3]
            self.modified = data[4]
            if not int(self.type):
                self.checksum = data[5]
            if data[6]:
                self.comment = data[6]
        except (KeyError, IndexError) as e:
            self.logger.error("stat: invalid response %s", e)
            return 0
        return 1

    def create(self):
        if not self.type:
            self.logger.error("create: non folder create requested: %s", self.path)
            return 0
        msg = "FOLDER %s" % self.path
        if not self.parent.socketthread.send(msg):
            self.logger.error("create: failed to send reqeuest")
            return 0
        error = self.parent.checkErrorMsg([516, 521])
        if error:
            self.logger.error("create: server returned error: %s on %s", error, self.path)
            return 0
        return 1

    def changeType(self, newType=False):
        if not self.path:
            self.logger.error("changeType: no path supplied")
        if not self.type:
            self.logger.error("changeType: Can only operate on folders: %s", self.path)
            return 0
        if not self.parent.privileges['alterFiles']:
            self.logger.error("Not allowed to change folder type: %s", self.path)
        if newType:
            self.type = newType
        msg = "TYPE " + str(self.path) + chr(28) + str(self.type)
        if not self.parent.socketthread.send(msg):
            self.logger.error("changeType: failed to send reqeuest")
            return 0
        error = self.parent.checkErrorMsg([516, 520])
        if error:
            self.logger.error("changeType: server returned error: %s on %s", error, self.path)
            return 0
        return 1

    def changeComment(self, suppliedComment=False):
        if not self.path:
            self.logger.error("comment: no path supplied")
        if not self.parent.privileges['alterFiles']:
            self.logger.error("Not allowed to comment on: %s", self.path)
        if suppliedComment:
            self.comment = suppliedComment
        msg = "COMMENT " + str(self.path) + chr(28) + str(self.comment)
        if not self.parent.socketthread.send(msg):
            self.logger.error("comment: failed to send reqeuest")
            return 0
        error = self.parent.checkErrorMsg([516, 520])
        if error:
            self.logger.error("comment: server returned error: %s on %s", error, self.path)
            return 0
        return 1

    def delete(self):
        if not self.path:
            self.logger.error("delete: no path supplied")
        if not self.parent.privileges['deleteFiles']:
            self.logger.error("Not allowed to delete %s", self.path)
        msg = "DELETE %s" % self.path
        if not self.parent.socketthread.send(msg):
            self.logger.error("delete: failed to send reqeuest")
            return 0
        error = self.parent.checkErrorMsg([516, 520])
        if error:
            self.logger.error("delete: server returned error: %s on %s", error, self.path)
            return 0
        return 1

    def queuedownload(self, targetpath):
        if not self.parent.privileges['download']:
            self.logger.error("Not allowed to download %s", self.path)
        self.offset, resume = (0, 0)
        if path.exists(targetpath + ".wiredTransfer"):
            ## partial file exists
            partfile = targetpath + ".wiredTransfer"
            try:
                size = os.stat(partfile).st_size
            except OSError:
                self.logger.error("queuedownload: Failed to read partial file %s", partfile)
                return 0
            if size >= 1048576:
                if not self.stat():
                    self.logger.error("queuedownload: failed to get server checksum for partial file %s", partfile)
                    return 0
                if self.checksum:
                    localchecksum = hashFile(partfile)
                    if not self.checksum == localchecksum:
                        self.logger.error("queuedownload: checksum mismatch for local file %s", partfile)
                        resume = 0
                    resume = 1
                    self.offset = size
            if path.exists(targetpath + ".wiredTransfer") and not resume:
                ## local file to small for checksuming or invalid checksum - discard and start over
                try:
                    os.unlink(targetpath + ".wiredTransfer")
                except OSError:
                    self.logger.error("queuedownload: failed to delete partial file %s", targetpath + ".wiredTransfer")
                    return 0
                self.offset = 0
        with self.parent.lock:
            self.parent.transfers[self.path] = transferObject(self.parent, self.size, 0,
                                                              targetpath, self.path, self.offset, self.transferParent)
        return 1

    def queueupload(self, localpath):
        self.offset = 0
        if not self.parent.privileges['upload']:
            self.logger.error("Not allowed to upload %s", self.path)
        with self.parent.lock:
            self.parent.transfers[self.path] = transferObject(self.parent, self.size, 1,
                                                              localpath, self.path, self.offset, self.transferParent)
        return 1

    def transferParenthook(self, parent):
        self.transferParent = parent


class wiredtransfer():
    def __init__(self, parent, lpath, rpath):
        self.parent = parent
        self.logger = self.parent.logger
        self.lock = threading.RLock()
        self.localpath = lpath
        self.localtarget = lpath
        self.remotepath = rpath
        self.remotetarget = rpath
        self.type = 0
        self.trtype = 0
        self.files = {}
        self.folders = {}
        self.queue = {}

    def initDownload(self):
        self.trtype = 0
        rpath = wiredfile(self.parent)
        rpath.path = self.remotepath
        if not rpath.stat():
            self.logger.error("initDownload: %s does not exist on server", self.remotepath)
            return 0
        self.type = int(rpath.type)
        if self.type:  # folder
            del(rpath)
            data = self.parent.listDirectory(self.remotepath, True)
            if data:
                for adata in data:
                    if int(adata.type):
                        self.folders[adata.path] = adata
                    else:
                        self.files[adata.path] = adata
                ## create local environment
                if not self.createLocalPath():
                    self.logger.error("Failed to create local path %s", self.localpath)
                    return 0
                ## queue download of files
                for akey, afile in self.files.items():
                    with self.lock:
                        localpath = path.join(self.localtarget, path.relpath(afile.path, self.remotepath))
                        if path.exists(localpath):
                            afile.stat()
                            if afile.checksum:
                                if afile.checksum == hashFile(localpath):
                                    # skiphook
                                    self.addQueued(afile.path, afile.size, 2)
                                    continue
                        afile.transferParenthook(self)
                        afile.queuedownload(localpath)
                        self.addQueued(afile.path, afile.size, 0)

        else:
            localpath = path.join(self.localtarget, path.basename(rpath.path))
            rpath.queuedownload(localpath)
        return 1

    def initUpload(self):
        self.trtype = 1
        if path.isdir(self.localpath):  # folder
            self.remotetarget = path.join(self.remotepath, path.basename(self.localpath))
            filelist = self.parent.listDirectory(self.remotepath, True)
            self.type = 1   # set folder bit
            for dirpath, dirnames, filenames in walk(self.localpath):
                if dirpath:
                        apath = path.relpath(dirpath, self.localpath)
                        if pathinfilelist(filelist, path.join(self.remotetarget, apath)):
                            pass  # directory already exists on server
                        elif apath != '.':
                            self.folders[apath] = apath
                if filenames:
                    for afilename in filenames:
                        remotepath = path.join(self.remotetarget, path.relpath(dirpath, self.localpath), afilename)
                        remotepath = pathinfilelist(filelist, remotepath)
                        if remotepath:  # file already exists on server
                            ## maybe compare checksums here (optionally?)
                            self.addQueued(remotepath.path, remotepath.size, 2)
                        elif not '.' in afilename[:1]:
                            afile = path.join(self.localpath, dirpath, afilename)
                            self.files[afile] = path.relpath(afile, self.localpath)
            if not self.createRemotePath():
                self.logger.error("initUpload: failed to create remote folder envoirnment")
            for akey, afile in self.files.items():
                with self.lock:
                    self.files[akey] = wiredfile(self.parent)
                    self.files[akey].size = os.stat(akey).st_size
                    self.files[akey].path = path.join(self.remotetarget, afile)
                    self.files[akey].transferParenthook(self)
                    if self.files[akey].queueupload(akey):
                        self.addQueued(self.files[akey].path, self.files[akey].size, 0)

        else:  # single file
            file = wiredfile(self.parent)
            file.size = os.stat(self.localpath).st_size
            file.path = path.join(self.remotepath, path.basename(self.localpath))
            file.queueupload(self.localpath)
        return 1

    def createLocalPath(self):
        if self.type:  # is directory structure
            if not createdir(self.localpath):
                return 0
            self.localtarget = path.join(self.localpath, path.basename(self.remotepath))
            if not createdir(self.localtarget):  # create basepath
                return 0
            keys = sorted(self.folders, key=lambda key: self.folders[key])
            for akey in keys:
                if not createdir(path.join(self.localtarget, path.relpath(akey, self.remotepath))):
                    return 0
        return 1

    def createRemotePath(self):
        if self.type:  # is directory structure
            rpath = createRdir(self, self.remotepath)
            if not rpath:
                self.logger.error("initUpload: Failed to create %s", self.remotepath)
                return 0
            remotepath = path.join(rpath.path, path.basename(self.localpath))
            rpath = createRdir(self, remotepath)
            if not rpath:
                self.logger.error("initUpload: Failed to create %s", remotepath)
                return 0
            keys = sorted(self.folders, key=lambda key: self.folders[key])
            for akey in keys:
                rdir = createRdir(self, path.join(remotepath, akey))
                if not rdir:
                    self.logger.error("createRemotePath: failed to create %s", path.join(remotepath, akey))
                    return 0
            return 1

    def addQueued(self, path, size, status):
        with self.lock:
            if int(status) > 1:
                self.queue[path] = {'size': int(size), 'bytesdone': int(size), 'status': int(status)}
            else:
                self.queue[path] = {'size': int(size), 'bytesdone': 0, 'status': int(status)}
        return 1

    def status(self):
        status = {}
        status['totalfiles'] = len(self.queue)
        status['done'] = 0
        status['failed'] = 0
        status['skipped'] = 0
        status['bytes'] = 0
        status['bytesdone'] = 0
        status['rate'] = 0
        status['complete'] = 0
        with self.lock:
            for akey, aitem in self.queue.items():
                status['bytes'] += aitem['size']
                if aitem['status']:
                    status['done'] += 1
                    if aitem['status'] == 2:
                        status['skipped'] += 1
                    if aitem['status'] == 3:
                        status['failed'] += 1
                if 'rate' in aitem:
                    status['rate'] += aitem['rate']
                status['bytesdone'] += int(aitem['bytesdone'])
        if status['bytesdone'] == status['bytes']:
            status['complete'] = 1
        return status


class transferObject(threading.Thread):
    def __init__(self, parent, size, trtype, lpath, rpath, offset, transfermonitor=0):
        threading.Thread.__init__(self)
        self.parent = parent
        self.transfermonitor = transfermonitor
        self.lock = threading.Lock()
        self.trtype = trtype  # 0 download / 1 upload
        self.lpath = lpath
        self.rpath = rpath
        self.id = 0
        self.queuepos = -1

        self.active = 0
        self.failed = 0
        self.offset = offset
        self.checksum = 0
        self.keepalive = 1
        self.bytestotal = int(size)
        self.bytesdone = 0
        self.limit = 0
        self.rate = 0

        self.connected = 0
        self.address = self.parent.address
        self.port = int(self.parent.port) + 1

        self.tlssocket = 0
        self.socket = 0

    def run(self):
        self.socket = pysocket.socket(pysocket.AF_INET, pysocket.SOCK_STREAM)
        if pysocket.has_ipv6:
            try:
                self.socket = pysocket.socket(pysocket.AF_INET6, pysocket.SOCK_STREAM)
            except:
                pass
        if not self.id:
            self.parent.logger("Transfer started but no id!")
            self.failed = 1
            self.shutdown()

        self.parent.logger.info("Starting Transfer %s", self.id)
        if not self.connect():
            self.failed = 1
            self.shutdown()

        if not self.startTransfer():
            self.shutdown()

        if self.trtype:  # upload
            outfile = self.tlssocket
            try:
                infile = open(str(self.lpath), 'r')
            except Exception as e:
                self.parent.logger.error("Failed to open local file %s", self.lpath)
                self.failed = 1
                self.shutdown()
            if int(self.offset):
                self.parent.logger.error("Resuming %s - Seeking to byte %s", self.rpath, self.offset)
                infile.seek(int(self.offset))
                self.bytesdone = int(self.offset)

        else:  # download
            infile = self.tlssocket
            mode = 'wb'
            if self.offset:
                mode = 'ab'
            try:
                outfile = open(str(self.lpath) + ".wiredTransfer", mode)
            except Exception as e:
                self.parent.logger.error("Failed to open local file %s", self.lpath)
                self.failed = 1
                self.shutdown(3)
            if self.offset:
                self.parent.logger.error("Resuming %s - Seeking to byte %s", self.rpath, self.offset)
                outfile.seek(int(self.offset))
                self.bytesdone = int(self.offset)

        if not self.process(infile, outfile):
            self.parent.logger.error("Transfer %s failed", self.id)
            self.failed = 1
            self.shutdown()
        if not self.trtype:  # download - move temp file into place
            try:
                move(str(self.lpath) + ".wiredTransfer", str(self.lpath))
            except Exception as e:
                self.parent.logger.error("Failed to move transfer tempfile to %s", self.lpath)
                self.failed = 1
                self.shutdown(3)
        self.shutdown()

    def shutdown(self, reason=0):
        with self.lock:
            self.keepalive = 0
        self.parent.dequeueTransfer(self.rpath, reason)
        self.parent.logger.debug("Stop transfer thread %s", self.rpath)
        raise SystemExit

    def connect(self):
        try:
            self.socket = makeconn(self.address, self.port)
        except pysocket.error:
            self.parent.logger.error("Transfer: Failed to connect!")
            return 0
        try:
            self.tlssocket = ssl.wrap_socket(self.socket, server_side=False, ssl_version=ssl.PROTOCOL_TLSv1)
            #self.peercert = self.tlssocket.getpeercert(binary_form=True)
        except:
            return 0
        self.connected = 1
        return 1

    def sendRequest(self):
        self.active = 1
        if self.trtype:
            self.checksum = hashFile(self.lpath)
            if not self.checksum:
                self.parent.logger.error("sendRequest: Unable to hash local file: %s", self.lpath)
                return 0
            errorcodes = [516, 521, 522, 523]
            msg = "PUT " + str(self.rpath) + chr(28) + str(self.bytestotal) + chr(28) + str(self.checksum)
            if not self.parent.socketthread.send(msg):
                self.parent.logger.error("sendRequest: failed to send reqeuest")
                return 0
            if self.parent.checkErrorMsg([521]):
                self.parent.logger.error("queueupload: file %s already exists!", self.rpath)
                self.parent.dequeueTransfer(self.rpath)
                return 0
        else:
            errorcodes = [516, 520, 523]
            msg = "GET " + str(self.rpath) + chr(28) + str(self.offset)
            if not self.parent.socketthread.send(msg):
                self.parent.logger.error("queuedownload: failed to send reqeuest")
                return 0

        error = self.parent.checkErrorMsg(errorcodes)
        if error:
            self.parent.logger.error("sendRequest: server returned error %s", error)
        return 1

    def startTransfer(self):
        if not self.connected:
            self.parent.logger.error("startTransfer: not connected %s", self.id)
            return 0
        msg = "TRANSFER %s" % self.id
        try:
            self.tlssocket.send(msg + chr(4))
        except Exception as e:
            self.parent.logger.error("startTransfer: send error %s", e)
            return 0
        return 1

    def process(self, input, output):
        interval, data_count, lastbytes, sleep_for = (1.0, 0, 0, 0)
        time_next = time.time() + interval
        while self.keepalive:
            buf = ""
            try:
                buf = input.read(512)  # smaller chunks = smoother, more accurate
            except:
                break
            if not buf:  # empty string means dead socket or eof
                break
            data_count += len(buf)
            if time.time() >= time_next:
                with self.transfermonitor.lock:
                    self.transfermonitor.queue[self.rpath]['rate'] = self.rate
                    self.transfermonitor.queue[self.rpath]['bytesdone'] = self.bytesdone

            if self.limit and data_count >= self.limit * interval:
                lastbytes = data_count
                data_count = 0
                sleep_for = time_next - time.time()
                if sleep_for < 0:
                    sleep_for = 0
            elif not self.limit and time.time() >= time_next:
                self.rate = int(data_count)
                data_count = 0
                time_next = time.time() + interval

            if sleep_for > 0 and self.limit:
                time.sleep(sleep_for)
                time_next = time.time() + interval
                sleep_for = 0
                self.rate = lastbytes
            elif self.limit and time.time() > time_next:
                lastbytes = data_count
                data_count = 0
                self.rate = lastbytes
                time_next = time.time() + interval
            try:
                output.write(buf)
            except:
                break

            self.bytesdone += len(buf)

        if self.bytestotal == self.bytesdone:
            return 1
        return 0


def createdir(apath):
    if not path.exists(apath):
        try:
            mkdir(apath)
        except:
            return 0
    return 1


def createRdir(self, apath):
    rpath = wiredfile(self.parent)
    rpath.path = apath
    if not rpath.stat():
        rpath.type = 1
        # doesn't exist
        if not rpath.create():
            # failed to create
            return 0
    return rpath


def hashFile(target):
    hash = hashlib.sha1()
    try:
        with open(target, 'rb') as source:
            data = source.read(1048576)
    except IOError as e:
        return 0
    hash.update(data)
    return str(hash.hexdigest())


def pathinfilelist(filelist, path):
    for apath in filelist:
        if apath.path == path:
            return apath
    return 0
