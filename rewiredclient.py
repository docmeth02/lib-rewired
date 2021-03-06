import rewiredsocket
from wiredfiles import wiredfile, wiredtransfer
import types
import commandhandler
import threading
from time import sleep, time
from base64 import b64encode
from socket import SHUT_RDWR
from random import uniform
from os.path import exists
from traceback import print_exc
import platform
from logging import getLogger
import hashlib
try:
    # This will fail on python > 2.7
    from ssl import OPENSSL_VERSION
except:
    pass


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
        self.userorder = {}
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
        self.accountlist = types.accountlist(self)

        self.transfers = {}

        self.news = []
        self.newsdone = 0

        self.autoreconnect = 1
        self.autojoinprivatec = 1
        self.maxTransfers = 1

    def run(self):
        self.queuemonitor = threading.Timer(5, self.checkQueue)
        self.queuemonitor.start()
        while self.keepalive:
            if self.socketthread.connected:
                if not self.keepalive:
                    break
                if self.socketthread.event.isSet():
                    for id, amsg in self.socketthread.queue.items():
                        if amsg.type in self.subscriptions:
                            # skip ssWired html chat
                            if ord(amsg.msg[2][:1]) >= 128:
                                # maybe add callback in case something needs the html chat
                                continue
                            try:
                                for asubscriber in self.subscriptions[int(amsg.type)]:
                                    asubscriber(amsg)  # call callback
                            except Exception as e:
                                self.logger.debug("callback for %s failed: %s - %s" % (amsg.type, e, print_exc()))
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
                self.connected = 0  # make sure this gets set when being kicked or connection just dropped
                self.logger.debug("not connected")

                if self.loggedin and not self.connected:
                    msg = self.checkErrorMsg([306, 307], 1, True)  # maybe we got kicked or banned?
                    if msg:
                        if msg.type == 306:
                            self.handler.clientKicked(msg.msg)
                        elif msg.type == 307:
                            self.handler.clientBanned(msg.msg)

                    if "__ConnectionLost" in self.notifications:  # notify parent about being disconnected
                        for acallback in self.notifications["__ConnectionLost"]:
                            try:
                                acallback()
                            except:
                                pass

                if self.loggedin and not self.autoreconnect:
                    self.keepalive = 0
                    break

                if self.loggedin and self.autoreconnect:
                        self.loggedin = 0
                        while not self.loggedin and self.keepalive:
                            self.logger.debug("Starting reconnect ...")
                            self.reconnect()
                            if self.loggedin:
                                self.logger.debug("Reconnected successfully")
                                if "__Reconnected" in self.notifications:
                                    for acallback in self.notifications["__Reconnected"]:
                                        acallback()
                                break
                            else:
                                self.logger.debug("Reconnect failed")
                            sleep(uniform(1, 20))

                if not self.loggedin:
                    sleep(0.5)

            sleep(0.1)
        self.logger.debug("Exit librewired")
        self.queuemonitor.cancel()
        self.queuemonitor.join()
        if len(self.transfers):
            for akey, atransfer in self.transfers.items():
                with atransfer.lock:
                    atransfer.keepalive = 0
        if self.socketthread.is_alive():
            try:
                self.socketthread.socket.shutdown(SHUT_RDWR)  # close socket to raise exception
            except IOError:
                pass
        self.connected = 0
        if self.pingtimer:
            self.pingtimer.cancel()
            self.pingtimer.join(1)
        self.socketthread.keepalive = 0
        self.socketthread.join(1)
        raise SystemExit

    def subscribe(self, id, callback):
        if id in self.subscriptions:
            self.subscriptions[int(id)].append(callback)
            return 1
        self.subscriptions[int(id)] = [callback]
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
        if self.pingtimer:  # cancel our running ping timer
            self.pingtimer.cancel()
            self.pingtimer.join(3)
        self.socketthread.keepalive = 0
        self.socketthread.join(3)  # destroy existing socket
        self.socketthread = rewiredsocket.socket(self)  # create a new one
        self.socketthread.start()
        if not self.connect(self.address, self.port):
            return 0
        if not self.keepalive:  # shutdown?
                return 0
        self.userlist = {}
        self.topics = {}
        self.userorder = {}
        if not self.login(self.nick, self.username, self.password):
            return 0
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
        login = self.getMsg(201, 10)
        if not login:
            fail = self.getMsg(510, 1)
            if fail:
                self.logger.debug("Server returned 510 upon login")
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

    def hashPassword(self, supplied=False):
        if not self.password and not supplied:
            return 0
        hash = hashlib.sha1()
        if not supplied:
            hash.update(self.password)
            self.password = hash.hexdigest().lower()
        else:
            hash.update(supplied)
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
            from os import uname
            sysuname = uname()
            try:
                sysplatform['OS'] = sysuname[0]
                sysplatform['OSVersion'] = sysuname[2]
                sysplatform['ARCH'] = sysuname[4]
                sysplatform['TLSLib'] = OPENSSL_VERSION
            except:
                pass
        return "%s/%s (%s; %s; %s) (%s)" % (self.appname, self.version, sysplatform['OS'],
                                            sysplatform['OSVersion'], sysplatform['ARCH'], sysplatform['TLSLib'])

    def serverPing(self):
        if not self.keepalive:
            return 0
        self.pingtimer = threading.Timer(60.0, self.serverPing)
        self.pingtimer.start()
        self.socketthread.send("PING")
        return 1

    def updateQueue(self, id):
        self.socketthread.lock.acquire()
        self.socketthread.queue.pop(id)
        if not len(self.socketthread.queue):  # queue is empty
            self.socketthread.event.clear()
            self.logger.debug("Empty Queue")
        self.socketthread.lock.release()
        return 1

    def getMsg(self, msgtype, timeout=5):
        count = 0
        if type(msgtype) == int:
            msgtype = [msgtype]
        self.logger.debug("getMsg: timeout is: %s", timeout)
        while float(count) <= float(timeout):
            if self.socketthread.event.isSet():
                for id, amsg in self.socketthread.queue.items():
                    for atype in msgtype:
                        if amsg.type == atype:
                            self.updateQueue(id)
                            self.logger.debug("RETURNING EVENT")
                            return amsg
            sleep(0.1)
            count += 0.1
        self.logger.debug("EXITING Without EVENT")
        return 0

    def getMsgGroup(self, msgtype, endtype, timeout=5):
        self.logger.debug("getMsgGroup: timeout is: %s", timeout)
        group = {}
        count = 0
        while float(count) <= float(timeout):
            if self.socketthread.event.isSet():
                msgs = self.socketthread.queue.items()
                msgs.sort()  # Sort msgs by transaction id to prevent early termination msg mix-ups
                for id, amsg in msgs:
                    if amsg.type == msgtype:
                        self.updateQueue(id)
                        group[int(amsg.id)] = amsg
                    elif amsg.type == endtype:
                        self.updateQueue(id)
                        if group:
                            keys = sorted(group, key=group.get)
                            ordered = []
                            for akey in keys:
                                ordered.append(group[akey])
                            return ordered
                        return []
            sleep(0.1)
            count += 0.1
        self.logger.debug("EXITING Without Group Termination EVENT")
        return 0

    def checkErrorMsg(self, msgtypes, timeout=1, returnmsg=False):
        # since this blocks execution and we actually don't expect to receive an error the default timeout is low
        self.logger.debug("checkErrorMsg: timeout is: %s", timeout)
        if type(msgtypes) is not list:
            self.logger.error("checkErrorMsg: expected type list for msgtypes but got %s", type(msgtypes))
            return 0
        count = 0
        while float(count) <= float(timeout):
            if self.socketthread.event.isSet():
                msgs = self.socketthread.queue.items()
                msgs.sort()
                for id, amsg in msgs:
                    if amsg.type in msgtypes:
                        self.updateQueue(id)
                        self.logger.debug("checkErrorMsg: received error %s after %s seconds", amsg.type, count)
                        if returnmsg:
                            return amsg
                        return amsg.type
            count += 0.1
            sleep(0.1)
        self.logger.debug("checkErrorMsg: no error received after %s seconds", count)
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

    def sendChat(self, chatid, text, action=0, legacyonly=0):
        if not self.connected or not self.loggedin:
            self.logger.debug("sendChat: not connected or logged in properly")
            return 0
        if not chatid in self.activeChats:
            self.logger.debug("sendChat: not in chat %s", chatid)
            return 0
        command = "SAY "
        if action:
            command = "ME "
        if legacyonly:
            text = "%s %s" % (chr(14), text)
        if not self.socketthread.send(command + str(chatid) + chr(28) + text):
            return 0
        return 1

    def sendChatImage(self, chatid, text, image, sendlegacy=True):
        # expects %image% inside of text and replaces every occurrence with ssWired formatted image data
        # expects image to be type dict: {'type': 'png/jpg/gif', 'data': binaryimagedata }
        # to wrap a image url instead of sending the imagedata pass type:url data:yoururl
        # sendlegacy will send an additional line containing the image url (when type ==url) but hidden to ssWired Users
        if not self.connected or not self.loggedin:
            self.logger.debug("sendChatImage: not connected or logged in properly")
            return 0
        if not chatid in self.activeChats:
            self.logger.debug("sendChatImage: not in chat %s", chatid)
            return 0
        if image['type'] is 'url':
            if not self.sendChat(chatid, '%s<img src="%s"/>' % (chr(128), image['data'])):
                self.logger.error("sendChatImage: Failed to send msg to server")
                return 0
            if sendlegacy:
                self.sendChat(chatid, '%s (Get http://shaosean.tk/ssWired/ for inline images)'
                              % image['data'], legacyonly=1)
            return 1
        data = self.insertImageData(text, image)
        try:
            data = data.encode("UTF-8")
        except:
            pass
        if data:
            if not self.sendChat(chatid, chr(128) + data):
                self.logger.error("sendChatImage: Failed to send msg to server")
                return 0
            return 1
        return 0

    def insertImageData(self, text, image):
        if not 'type' in image or not 'data' in image:
            self.logger.debug("insertImageData: invalid image data")
            return 0
        data = b64encode(image['data'])
        imagestring = '%s<img src="data:image/%s;base64,%s"/>' % (unichr(128), image['type'].lower(), data)
        return text.replace('%image%', imagestring)

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
            self.logger.error("Can't invite user to private chat im not part off")
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

    def declinePrivateChat(self, chatid):
        if not self.connected or not self.loggedin:
            self.logger.debug("declinePrivateChat: not connected or logged in properly")
            return 0
        self.socketthread.send("DECLINE " + str(chatid))
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
        if chatid in self.userorder:
            self.userorder.pop(chatid)
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

    def sendPrivateMsgImage(self, userid, text, image):
        # expects %image% inside of text and replaces every occurrence with ssWired formatted image data
        # expects image to be type dict: {'type': 'png/jpg/gif', 'data': binaryimagedata }
        if not self.connected or not self.loggedin:
            self.logger.debug("sendChatImage: not connected or logged in properly")
            return 0
        data = self.insertImageData(text, image)
        try:
            data = data.encode("UTF-8")
        except:
            pass
        if data:
            if not self.socketthread.send("MSG " + str(userid) + chr(28) + chr(128) + data):
                self.logger.error("sendPrivateMsgImage: Failed to send msg to server")
                return 0
            return 1
        return 0

    def getUserList(self, chatid):
        # gets the initial userlist for a chat
        if not chatid in self.activeChats:
            return 0
        self.socketthread.send("WHO " + str(chatid))
        group = self.getMsgGroup(310, 311, 30)
        if not int(chatid) in self.userorder:
            self.userorder[int(chatid)] = []
        if not group:
            return 0
        for amsg in group:
            if int(chatid) == 1:  # public chat adds users to the global userlist
                auser = types.user()
                auser.initFromDict(amsg.msg)
                self.userlist[auser.userid] = auser
                with self.lock:
                    self.userorder[int(chatid)].append(int(auser.userid))
            else:
                userid = int(amsg.msg[1])
                if userid in self.userlist and userid != self.id:
                    self.logger.debug("Got User %s in chat %s", userid, chatid)
                    self.userlist[userid].chats.append(int(chatid))
                elif userid != self.id:
                    self.logger.error("Can't find user %s" % amsg.msg[1])
                    return 0
                with self.lock:
                    self.userorder[int(chatid)].append(userid)
        if "__UserListDone" in self.notifications:
            try:
                for acallback in self.notifications["__UserListDone"]:
                    acallback([int(chatid)])
            except:
                self.logger.debug("Error in callback for __UserListDone")
                return 0
        return 1

    def loadIcon(self, filename):
        try:
            self.icon = readIcon(filename)
        except:
            return 0
        if self.loggedin:
            self.socketthread.send("ICON 0" + chr(28) + self.icon)
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

    def setChatTopic(self, chat, topic):
        if not self.privileges['changeTopic']:
            self.logger.info("Not allowed to change Topic in chat %s", chat)
        if self.loggedin:
            if self.socketthread.send('TOPIC %s%s%s' % (chat, chr(28), topic)):
                return 1
        return 0

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
        fields = {0: 'user', 1: 'idle', 2: 'admin', 3: 'icon', 4: 'nick', 5: 'login', 6: 'ip', 7: 'host', 8:
                  'client-version', 9: 'cipher-name', 10: 'cipher-bits', 11: 'login-time', 12: 'idle-time', 13:
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

    def postNews(self, news):
        if not self.privileges['postNews']:
            self.logger.info("Not allowed to post news")
        if self.socketthread.send('POST %s' % news):
                return 1
        return 0

    def getNews(self):
        if self.socketthread.send('NEWS'):
                return 1
        return 0

    def clearNews(self):
        if not self.privileges['clearNews']:
            self.logger.info("Not allowed to clear news")
        if self.socketthread.send("CLEARNEWS"):
            self.news = []
            self.newsdone = 0
            self.getNews()
            return 1
        return 0

    def kickUser(self, id, msg=""):
        if not self.privileges['kickUsers']:
            self.logger.info("kick: insufficient privileges")
            return 0
        if not int(id) in self.userlist:
            self.logger.error("kick: invalid userid %s", id)
            return 0
        if not self.socketthread.send("KICK " + str(id) + chr(28) + str(msg)):
            self.logger.error("Failed to kick user %s", id)
            return 0
        self.logger.debug("Kicked user %s", id)
        return 1

    def banUser(self, id, msg=""):
        if not self.privileges['banUsers']:
            self.logger.info("ban: insufficient privileges")
            return 0
        if not int(id) in self.userlist:
            self.logger.error("ban: invalid userid %s", id)
            return 0
        if not self.socketthread.send("BAN " + str(id) + chr(28) + str(msg)):
            self.logger.error("Failed to ban user %s", id)
            return 0
        self.logger.debug("Banned user %s", id)
        return 1

## Accounts

    def getUserAccounts(self):
        if not self.privileges['editAccounts']:
            self.logger.error("getUserAccounts: Not allowed to read accounts")
            return 0
        if not self.socketthread.send("USERS"):
            self.logger.error("getAccountList: Failed to send USERS")
        data = self.getMsgGroup(610, 611, 5)
        if data:
            if not self.accountlist:
                self.accountlist = types.accountlist()
            self.accountlist.updateUsers(data)
        else:
            self.logger.error("Failed to update user accounts")
        return 1

    def getGroupAccounts(self):
        if not self.privileges['editAccounts']:
            self.logger.error("getGroupAccounts: Not allowed to read accounts")
            return 0
        if not self.socketthread.send("GROUPS"):
            self.logger.error("getAccountList: Failed to send USERS")
        data = self.getMsgGroup(620, 621, 5)
        if data:
            self.accountlist.updateGroups(data)
        else:
            self.logger.error("Failed to update group accounts")
        return 1

    def loadAccountList(self):
        if not self.privileges['editAccounts']:
            self.logger.error("loadAccountList: Not allowed to read accounts")
            return 0
        if not self.getGroupAccounts():
            self.logger.error("loadAccountList: failed to read groups")
            return 0

        if not self.getUserAccounts():
            self.logger.error("loadAccountList: failed to read users")
            return 0

        for agroup in self.accountlist.groups:
            if not self.accountlist.loadGroup(agroup):
                self.logger.error("loadAccountList: failed to read group %s", agroup)
                continue

        for auser in self.accountlist.users:
            if not self.accountlist.loadUser(auser):
                self.logger.error("loadAccountList: failed to read user %s", auser)
                continue

        self.logger.debug("loadAccountList: loaded %s groups and %s users", len(self.accountlist.groups),
                          len(self.accountlist.users))
        self.accountlist.lastupdated = time()
        return 1

    def createUser(self, username, password, privs, groupmember=False):
        if not self.privileges['createAccounts']:
            self.logger.error("createUser: Not allowed to add new accounts")
            return 0
        if username in self.accountlist.users:
            self.logger.error("User %s already exists", username)
            return 0
        group = ''
        password = self.hashPassword(password)
        if groupmember:
            if groupmember in self.accountlist.groups:
                group = groupmember
            else:
                self.logger.error("Asked to add user %s as a member of group %s. But group doesn't exist",
                                  username, groupmember)
                return 0
        msg = "CREATEUSER " + str(username) + chr(28) + str(password) + chr(28)\
            + str(group) + chr(28) + str(privs.toString())
        if not self.socketthread.send(msg):
            self.logger.error("createUser: failed to send message")
        error = self.checkErrorMsg([514, 516])
        if error:
            self.logger.error("createUser: server returned error %s", error)
            return 0
        if group:
            if group in self.accountlist.groups:
                if not username in self.accountlist.groups[group].members:
                    self.accountlist.groups[group].members.append(username)
        self.getUserAccounts()
        self.accountlist.loadUser(username)
        return 1

    def createGroup(self, groupname, privs):
        if not self.privileges['createAccounts']:
            self.logger.error("createGroup: Not allowed to add new accounts")
            return 0
        if groupname in self.accountlist.groups:
            self.logger.error("Group %s already exists", groupname)
            return 0
        msg = "CREATEGROUP " + str(groupname) + chr(28) + str(privs.toString())
        if not self.socketthread.send(msg):
            self.logger.error("createGroup: failed to send message")
        error = self.checkErrorMsg([514, 516])
        if error:
            self.logger.error("createGroup: server returned error %s", error)
            return 0
        self.getGroupAccounts()
        self.accountlist.loadGroup(groupname)
        return 1

    def deleteUser(self, username):
        if not self.privileges['deleteAccounts']:
            self.logger.error("deleteUser: Not allowed to delete accounts")
            return 0
        if not username in self.accountlist.users:
            self.logger.error("deleteUser: Unkown user %s", username)
            return 0
        if self.accountlist.users[username].group:
            group = self.accountlist.users[username].group
        else:
            group = 0
        msg = "DELETEUSER %s" % username
        if not self.socketthread.send(msg):
            self.logger.error("deleteUser: failed to send message")
        error = self.checkErrorMsg([513, 516])
        if error:
            self.logger.error("deleteUser: server returned error %s", error)
            return 0
        if group in self.accountlist.groups:
            if username in self.accountlist.groups[group].members:
                self.accountlist.groups[group].members.remove(username)
        return 1

    def deleteGroup(self, groupname):
        if not self.privileges['deleteAccounts']:
            self.logger.error("deleteGroup: Not allowed to delete accounts")
            return 0
        if not groupname in self.accountlist.groups:
            self.logger.error("deleteGroup: Unkown group %s", groupname)
            return 0
        if len(self.accountlist.groups[groupname].members):
            self.logger.error("deleteGroup: Can't delete non empty group %s", groupname)
            return 0
        msg = "DELETEGROUP %s" % groupname
        if not self.socketthread.send(msg):
            self.logger.error("deleteGroup: failed to send message")
        error = self.checkErrorMsg([513, 516])
        if error:
            self.logger.error("deleteGroup: server returned error %s", error)
            return 0
        return 1

    def updateUser(self, username):
        if not self.privileges['editAccounts']:
            self.logger.error("updateUser: Not allowed to modify accounts")
            return 0
        if not username in self.accountlist.users:
            self.logger.error("updateUser: Unkown user %s", username)
            return 0
        user = self.accountlist.users[username]
        if not user.group:
            group = ''
        else:
            group = user.group
        msg = "EDITUSER " + str(user.username) + chr(28) + str(user.password) + chr(28)\
            + str(group) + chr(28) + str(user.privs.toString())
        if not self.socketthread.send(msg):
            self.logger.error("updateUser: failed to send message")
        error = self.checkErrorMsg([513, 516])
        if error:
            self.logger.error("updateUser: server returned error %s", error)
            return 0
        return 1

    def updateGroup(self, groupname):
        if not self.privileges['editAccounts']:
            self.logger.error("updateGroup: Not allowed to modify accounts")
            return 0
        if not groupname in self.accountlist.groups:
            self.logger.error("updateGroup: Unkown group %s", groupname)
            return 0
        group = self.accountlist.groups[groupname]
        msg = "EDITGROUP " + str(group.groupname) + chr(28) + str(group.privs.toString())
        if not self.socketthread.send(msg):
            self.logger.error("updateGroup: failed to send message")
        error = self.checkErrorMsg([513, 516])
        if error:
            self.logger.error("updateGroup: server returned error %s", error)
            return 0
        return 1

## Files
    def search(self, query):
        result = []
        if not self.socketthread.send("SEARCH %s" % query):
            self.logger.error("search: failed to send message")
        data = self.getMsgGroup(420, 421, 20)
        if not data:
            self.logger.info("search: No results for %s", query)
            return 0
        for amsg in data:
            result.append(wiredfile(self, amsg.msg))
        return result

    def listDirectory(self, path, recursive=False):
        msg = "LIST %s" % path
        if recursive:
            msg = "LISTRECURSIVE %s" % path
        if not self.socketthread.send(msg):
            self.logger.error("listDirectory: failed to send message")
        data = self.getMsgGroup(410, 411, 10)
        if not type(data) is list:
            error = self.checkErrorMsg([520])
            if error:
                self.logger.error("listDirectory: server returned error: %s for dir %s", error, path)
            return 0
        filelist = []
        for amsg in data:
            filelist.append(wiredfile(self, amsg.msg))
        return filelist

    def createFolder(self, path, foldertype=1):
        # check path in upload folder here
        if not self.privileges['createFolders']:
            self.logger.error("createFolder: Not allowed to create new folders")
            return 0
        folder = wiredfile(self)
        folder.type = foldertype
        folder.path = path
        if not folder.create():
            return 0
        if folder.type > 1:
            if not folder.changeType(foldertype):
                return 0
        if not folder.stat():
            return 0
        return folder

    def delete(self, path):
        if not self.privileges['deleteFiles']:
            self.logger.error("delete: Not allowed to create delete files")
            return 0
        target = wiredfile(self)
        target.path = path
        if not target.delete():
            return 0
        return 1

    def move(self, oldpath, newpath):
        if not self.privileges['alterFiles']:
            self.logger.error("move: Not allowed to create delete files")
            return 0
        target = wiredfile(self)
        target.path = oldpath
        if not target.move(newpath):
            return 0
        return target

    def stat(self, rpath):
        target = wiredfile(self)
        target.path = rpath
        if target.stat():
            return target
        return 0

    def changeType(self, path, foldertype):
        # check path in upload folder here
        if not self.privileges['alterFiles']:
            self.logger.error("changeType: Not allowed to alter folders")
            return 0
        folder = wiredfile(self)
        folder.type = int(foldertype)
        folder.path = path
        if not folder.changeType(foldertype):
                return 0
        return folder

    def changeComment(self, path, newcomment):
        # check path in upload folder here
        if not self.privileges['alterFiles']:
            self.logger.error("changeComment: Not allowed to alter comments")
            return 0
        obj = wiredfile(self)
        obj.comment = newcomment
        obj.path = path
        if not obj.changeComment():
                return 0
        return obj

    def download(self, lpath, rpath):
        downloader = wiredtransfer(self, lpath, rpath)
        downloader.initDownload()
        return downloader

    def upload(self, lpath, rpath):
        uploader = wiredtransfer(self, lpath, rpath)
        uploader.initUpload()
        return uploader

    def activeTransfers(self, trtype):
        active = 0
        with self.lock:
            for akey, atransfer in self.transfers.items():
                if atransfer.trtype == trtype and (atransfer.active or atransfer.id):
                    active += 1
        return active

    def dequeueTransfer(self, name, reason=0):
        if not name in self.transfers:
            self.logger.error("dequeueTransfer: invalid transfer %s specified", name)
            return 0
        try:
            item = 0
            item = self.transfers[name].transfermonitor.queue[name]
        except KeyError:
            self.logger.error("dequeueTransfer: invalid key %s", name)
        if not reason and item:
            with self.transfers[name].transfermonitor.lock:
                item['bytesdone'] = item['size']
                if 'rate' in item:
                    del(item['rate'])
                item['status'] = 1
        elif reason == 2 and item:
            item['bytesdone'] = item['size']
            item['status'] = 2
        elif reason == 3 and item:
            item['bytesdone'] = item['size']
            item['status'] = 3
        with self.lock:
            if name in self.transfers:
                del(self.transfers[name])
        self.checkQueue(True)
        return 1

    def checkQueue(self, once=False):
        for trtype in (0, 1):
            if len(self.transfers):
                for akey, atransfer in self.transfers.items():
                    if self.activeTransfers(trtype) >= self.maxTransfers:
                        break
                    if atransfer.trtype == trtype and not atransfer.active:
                        with atransfer.lock:
                            atransfer.active = 1
                            atransfer.sendRequest()
                        break
        if not once:
            self.queuemonitor = threading.Timer(5, self.checkQueue)
            self.queuemonitor.start()
        return 1

    def logout(self):
        for achat in self.activeChats:
            if not self.socketthread.send("LEAVE %s" % achat):
                self.logger.error("Failed to leave chat %s", achat)
        self.activeChats = []
        self.disconnect()
        self.socketthread.keepalive = 0
        return 1


def readIcon(filename):
    icon = ''
    if not exists(filename):
        return 0
    with open(filename, "rb") as f:
        data = f.read(1)
        while data:
            icon += data
            data = f.read(1024)
    icon = b64encode(icon)
    return icon
