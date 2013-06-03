class wiredfile():
    def __init__(self, parent, data=False):
        self.parent = parent
        self.path = ""
        self.type = None
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
                self.parent.logger("wiredfile: failed to init from supplied dataset: %s", e)

    def stat(self):
        if not self.path:
            return 0
        msg = "STAT %s" % self.path
        if not self.parent.socketthread.send(msg):
            self.parent.logger.error("stat: failed to send msg to server")
            return 0
        data = self.parent.getMsg(402, 10)
        if not data:
            self.parent.logger.error("stat: request for %s timed out", self.path)
            return 0
        data = data.msg
        if not data[0] == self.path:
            self.parent.logger.error("stat: requested info for %s got %s!", self.path, data[0])
        try:
            self.size = data[2]
            self.created = data[3]
            self.modified = data[4]
            if not self.type:
                self.checksum = data[5]
            if data[6]:
                self.comment = data[6]
        except (KeyError, IndexError) as e:
            self.parent.logger.error("stat: invalid response %s", e)
            return 0
        return 1

    def create(self):
        if self.type != 1:
            self.parent.logger.error("create: non folder create requested: %s", self.path)
            return 0
        msg = "FOLDER %s" % self.path
        if not self.parent.socketthread.send(msg):
            self.parent.logger.error("creat: failed to send reqeuest")
            return 0
        error = self.parent.checkErrorMsg([516, 521])
        if error:
            self.parent.logger.error("create: server returned error: %s on %s", error, self.path)
            return 0
        return 1
