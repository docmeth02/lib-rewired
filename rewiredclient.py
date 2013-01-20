import rewiredsocket
import types
import commandhandler
import threading
from time import sleep
from ssl import OPENSSL_VERSION
from base64 import b64encode
from socket import SHUT_RDWR
from os import uname
#from platform import platform
import platform
from logging import getLogger
import hashlib


class client(threading.Thread):
    def __init__(self, parent):
        threading.Thread.__init__(self)
        self.lock = threading.Lock()
        self.parent = parent
        self.appname = 'lib:re:wired'
        self.version = 0.1
        self.wiredmessages = types.wiredMessages()
        self.logger = getLogger('lib:re:wired')
        self.keepalive = 1
        self.socketthread = rewiredsocket.socket(self)
        self.socketthread.start()
        self.pingtimer = 0
        self.address = 0
        self.privileges = 0
        self.port = 0
        self.handler = commandhandler.Handler(self)
        self.userlist = {}
        self.subscriptions = {}
        self.notifications = {}
        self.serverinfo = {}
        self.topics = {}
        self.activeChats = []
        self.id = 0
        self.nick = 0
        self.username = 0
        self.password = 0
        self.icon = 0
        self.status = 0
        self.connected = 0
        self.loggedin = 0

        self.autoreconnect = 1

    def run(self):
        while self.keepalive:
            if self.socketthread.connected:
                event = self.socketthread.event.wait(0.1)
                if not self.keepalive:
                    break
                if event:
                    for id, amsg in self.socketthread.queue.items():
                        if amsg.type in self.subscriptions:
                            try:
                                self.subscriptions[amsg.type](amsg)  # call callback
                            except '' as e:
                                self.logger.debug("callback for %s failed!", amsg.type)
                            self.updateQueue(id)
                            break
                        elif self.wiredmessages.askhandle(amsg.type):
                            self.logger.debug(str(amsg.type) + " is handled internally")
                            self.handler.process(amsg)
                            self.updateQueue(id)
                            break
                        else:
                            sleep(0.1)
            else:  # socket is not connected
                self.logger.debug("not connected")
                if self.autoreconnect:
                    if self.username and self.password != 0 and self.address\
                    and self.port and not self.socketthread.is_alive():
                        self.reconnect()
            sleep(0.1)
        self.logger.debug("EXIT")
        if self.socketthread.is_alive():
            try:
                self.socketthread.socket.shutdown(SHUT_RDWR)  # close socket to raise exception
            except IOError:
                pass
        if self.pingtimer:
            self.pingtimer.cancel()
            self.pingtimer.join()
        self.socketthread.keepalive = 0
        self.socketthread.join(1)
        raise SystemExit

    def subscribe(self, id, callback):
        self.subscriptions[int(id)] = callback
        return 1

    def notify(self, event, callback):
        if event in self.notifications:
            self.notifications[event].append(callback)
            return 1
        self.notifications[event] = [callback]
        return 1

    def connect(self, server, port):
        self.address = server
        self.port = port
        if not self.socketthread.connect(server, port):
            return 0
        self.connected = 1
        return 1

    def reconnect(self):
        if self.pingtimer:
            self.pingtimer.cancel()
            self.pingtimer.join()
        self.socketthread = rewiredsocket.socket(self)
        self.socketthread.start()
        while not self.socketthread.connected and self.keepalive:
            if not self.connect(self.address, self.port):
                sleep(2)
                continue
            if not self.keepalive:
                return 0
            self.userlist = {}
            self.topics = {}
            if not self.login(self.nick, self.username, self.password):
                self.logger.debug("reconnect login failed")
            continue
        self.logger.debug("reconnected")
        return 1

    def disconnect(self):
        if not self.socketthread.disconnect():
            return 0
        self.connected = 0
        return 1

    def login(self, nick, user, passw, clearPass=0):
        self.nick = nick
        self.username = user
        self.password = passw
        if clearPass:
            self.hashPassword()
        self.socketthread.send("HELLO")
        self.socketthread.send("NICK " + self.nick)
        self.socketthread.send("CLIENT " + self.clientString())
        if self.status:
            self.socketthread.send("STATUS " + self.status)
        if self.icon:
            self.socketthread.send("ICON 0" + chr(28) + self.icon)
        self.socketthread.send("USER " + self.username)
        self.socketthread.send("PASS " + self.password)
        login = self.getMsg(201)
        if not login:
            self.logger.debug("login failed!")
            return 0
        self.id = int(login.msg[0])
        self.logger.debug("Login successful. User ID: %s", self.id)
        self.loggedin = 1  # login successful
        self.activeChats.append(1)  # public chat
        self.socketthread.send("BANNER")
        self.socketthread.send("PRIVILEGES")
        self.serverPing()
        self.getUserList(1)
        return 1

    def hashPassword(self):
        if not self.password:
            return 0
        hash = hashlib.sha1()
        hash.update(self.password)
        self.password = hash.hexdigest().lower()
        return hash.hexdigest().lower()

    def clientString(self):
        sysplatform = {'OS': "unkown", 'OSVersion': "unkown", 'ARCH': "unkown", 'TLSLib': "unkown"}
        if platform.system() == "Windows":
            try:
                sysplatform['OS'] = platform.system()
                sysplatform['OSVersion'] = platform.version()
                sysplatform['ARCH'] = platform.machine()
                sysplatform['TLSLib'] = OPENSSL_VERSION
            except:
                pass
        else:
            sysuname = uname()
            try:
                sysplatform['OS'] = sysuname[0]
                sysplatform['OSVersion'] = sysuname[2]
                sysplatform['ARCH'] = sysuname[4]
                sysplatform['TLSLib'] = OPENSSL_VERSION
            except:
                pass
        return "%s/%s (%s; %s; %s) (%s)" % (self.appname, self.version, sysplatform['OS'],\
                                            sysplatform['OSVersion'], sysplatform['ARCH'], sysplatform['TLSLib'])

    def serverPing(self):
        if not self.keepalive:
            return 0
        self.pingtimer = threading.Timer(60.0, self.serverPing)
        self.pingtimer.start()
        self.socketthread.send("PING")
        return 1

    def updateQueue(self, id):
        alreadyLocked = 0
        if not self.socketthread.lock.acquire(False):
            alreadyLocked = 1
        self.socketthread.queue.pop(id)
        if not len(self.socketthread.queue):  # queue is empty
            self.socketthread.event.clear()
            self.logger.debug("Empty Queue")
        if not alreadyLocked:
            self.socketthread.lock.release()
        return 1

    def getMsg(self, type, timeout=5):
        count = 0
        self.logger.debug("timeout is: %s", timeout)
        while float(count) <= float(timeout):
            event = self.socketthread.event.wait(0)
            if event:
                for id, amsg in self.socketthread.queue.items():
                    if amsg.type == type:
                        self.updateQueue(id)
                        self.logger.debug("RETURNING EVENT")
                        return amsg
            sleep(0.1)
            count += 0.1
        self.logger.debug("EXITING Without EVENT")
        return 0

    def getMsgGroup(self, msgtype, endtype, timeout=5):
        self.logger.debug("timeout is: %s", timeout)
        group = {}
        count = 0
        while float(count) <= float(timeout):
            event = self.socketthread.event.wait()
            if event:
                self.socketthread.lock.acquire()
                for id, amsg in self.socketthread.queue.items():
                    if amsg.type == msgtype:
                        self.updateQueue(id)
                        group[int(amsg.id)] = amsg
                    elif amsg.type == endtype:
                        self.updateQueue(id)
                        self.socketthread.lock.release()
                        return group
                self.socketthread.lock.release()
            sleep(0.1)
            count += 0.1
        self.logger.debug("EXITING Without Group Termination EVENT")
        return 0

    def changeNick(self, newNick):
        if not self.connected or not self.loggedin:
            self.logger.debug("changeNick: not connected or logged in properly")
            return 0
        if not self.socketthread.send("NICK " + str(newNick)):
            self.logger.error("Failed to send NICK command!")
            return 0
        return 1

    def changeStatus(self, newStatus):
        if not self.connected or not self.loggedin:
            self.logger.debug("changeStatus: not connected or logged in properly")
            return 0
        if not self.socketthread.send("STATUS " + str(newStatus)):
            self.logger.error("Failed to send STATUS command!")
            return 0
        return 1

    def sendChat(self, chatid, text, action=0):
        if not self.connected or not self.loggedin:
            self.logger.debug("sendChat: not connected or logged in properly")
            return 0
        if not chatid in self.activeChats:
            self.logger.debug("sendChat: not in chat %s", chatid)
            return 0
        command = "SAY "
        if action:
            command = "ME "
        if not self.socketthread.send(command + str(chatid) + chr(28) + str(text)):
            return 0
        return 1

    def startPrivateChat(self):
        if not self.connected or not self.loggedin:
            self.logger.debug("startPrivateChat: not connected or logged in properly")
            return 0
        self.socketthread.send("PRIVCHAT")
        response = self.getMsg(330, 1)
        if not response:
            self.logger.error("No reply to PRIVCHAT")
            return 0
        try:
            chatid = int(response.msg[0])
        except:
            self.logger.error("Invalid private chat id in startPrivateChat")
            return 0
        self.activeChats.append(chatid)
        self.getUserList(chatid)
        return chatid

    def invitePrivateChat(self, chatid, userid):
        if not self.connected or not self.loggedin:
            self.logger.debug("startPrivateChat: not connected or logged in properly")
            return 0
        if not chatid in self.activeChats:
            self.error("Can't invite user to private chat im not part off")
            return 0
        self.socketthread.send("INVITE " + str(userid) + chr(28) + str(chatid))
        return 1

    def joinPrivateChat(self, chatid):
        if not self.connected or not self.loggedin:
            self.logger.debug("joinPrivateChat: not connected or logged in properly")
            return 0
        self.socketthread.send("JOIN " + str(chatid))
        self.activeChats.append(chatid)
        self.getUserList(chatid)
        return 1

    def leaveChat(self, chatid):
        chatid = int(chatid)
        if not self.connected or not self.loggedin:
            self.logger.debug("joinPrivateChat: not connected or logged in properly")
            return 0
        if not chatid in self.activeChats:
            self.logger.error("asked to leave %s but we're not in that chat!")
            return 0
        self.socketthread.send("LEAVE " + str(chatid))
        self.activeChats.remove(chatid)
        if chatid in self.topics:
            self.logger.debug("releasing topic for chat %s", chatid)
            try:
                self.topics.pop(chatid)
            except:
                self.logger.error("Failed to release topic for chat %s", chatid)
                return 0
        return 1

    def sendPrivateMsg(self, userid, text):
        if not self.connected or not self.loggedin:
            self.logger.debug("joinPrivateChat: not connected or logged in properly")
            return 0
        self.socketthread.send("MSG " + str(userid) + chr(28) + str(text))
        return 1

    def getUserList(self, chatid):
        # gets the initial userlist for a chat
        if not chatid in self.activeChats:
            return 0
        self.socketthread.send("WHO " + str(chatid))
        group = self.getMsgGroup(310, 311)
        if not group:
            return 0
        for id, amsg in group.items():
            if int(chatid) == 1:  # public chat adds users to the global userlist
                auser = types.user()
                auser.initFromDict(amsg.msg)
                self.logger.debug("Found User: " + str(auser.nick) + " id:" + str(auser.userid))
                self.userlist[auser.userid] = auser
            else:
                userid = int(amsg.msg[1])
                if userid in self.userlist and userid != self.id:
                    self.logger.debug("Got User %s in chat %s", userid, chatid)
                    self.userlist[userid].chats.append(int(chatid))
                elif userid != self.id:
                    self.logger.error("Can't find user %s" % amsg.msg[1])
                    return 0
        return 1

    def loadIcon(self, filename):
        try:
            with open(filename, 'r') as iconFile:
                self.icon = b64encode(iconFile.read())
        except:
            return 0
        return 1

    def getUserByID(self, id):
        try:
            return self.userlist[int(id)]
        except KeyError:
            self.logger.error("getUserByID: Invalid User %s", id)
            return 0

    def getUserNameByID(self, id):
        id = int(id)
        if not id in self.userlist:
            return 0
        user = self.userlist[id].login
        return user

    def getNickByID(self, id):
        id = int(id)
        if not id in self.userlist:
            return 0
        nick = self.userlist[id].nick
        return nick

    def getUserByName(self, name):
        for index, auser in self.userlist.items():
            if auser.login.upper() == name.upper():
                return auser.userid
        return 0

    def getUserByNick(self, nick):
        for index, auser in self.userlist.items():
            if auser.nick.upper() == nick.upper():
                return auser.userid
        return 0

    def getChatUsers(self, chatid):
        userlist = []
        if not self.userlist:
            return 0
        for userid, user in self.userlist.items():
            if int(chatid) in user.chats:
                userlist.append(int(userid))
        return userlist

    def getUserInfo(self, id):
        if not int(id) in self.userlist:
            return 0
        if not self.privileges:
            return 0
        if not self.privileges['getUserInfo']:
            self.logger.info("Not allowed to get user info on this server")
            return 0
        if not self.socketthread.send("INFO %s" % id):
            self.logger.error("Error while sending INFO %s", id)
        userinfo = self.getMsg(308)
        if not userinfo:
            self.logger.error("Timeout while waiting for userinfo on user %s", id)
            return 0
        info = {}
        fields = {0: 'user', 1: 'idle', 2: 'admin', 3: 'icon', 4: 'nick', 5: 'login', 6: 'ip', 7: 'host', 8: \
                  'client-version', 9: 'cipher-name', 10: 'cipher-bits', 11: 'login-time', 12: 'idle-time', 13: \
                  'downloads', 14: 'uploads', 15: 'status', 16: 'image'}
        for key, fieldname in fields.items():
            try:
                info[fieldname] = userinfo.msg[key]
            except KeyError:
                self.logger.error("Invalid field in getUserInfo: %s", fieldname)
                return 0
        if info['downloads']:
            info['downloads'] = self.splitTransfer(info['downloads'])
        if info['uploads']:
            info['uploads'] = self.splitTransfer(info['uploads'])
        if int(info['user']) in self.userlist:
            self.userlist[int(info['user'])].updateFromUserInfo(info)
        return info

    def splitTransfer(self, data):
        transfers = {}
        data = data.split(chr(29))
        index = 0
        for atransfer in data:
            atransfer = atransfer.split(chr(30))
            if len(atransfer) != 4:
                self.logger.error("invalid field count in splitTransfer")
                break
            try:
                thistransfer = {}
                thistransfer['path'] = atransfer[0]
                thistransfer['transferred'] = atransfer[1]
                thistransfer['size'] = atransfer[2]
                thistransfer['speed'] = atransfer[3]
            except IndexError:
                self.logger.debug("Invalid field count in splitTransfer! %s", key)
                break
            transfers[index] = thistransfer
            index += 1
        return transfers
