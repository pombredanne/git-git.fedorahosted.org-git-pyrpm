#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Library General Public License as published by
# the Free Software Foundation; version 2 only
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
# Copyright 2004 Red Hat, Inc.
#
# Author: Phil Knirsch, Thomas Woerner, Florian La Roche
#


import gzip, types
from struct import pack,unpack
from base import *
from functions import *
from cpio import *


class RpmIO:
    """'Virtual' IO Class for RPM packages and data"""
    def __init__(self, source):
        self.source = source

    def open(self):
        return 0

    def read(self):
        return 0

    def write(self):
        return 0

    def close(self):
        return 0


class RpmStreamIO(RpmIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmIO.__init__(self, source)
        self.fd = None
        self.cpiofd = None
        self.cpio = None
        self.verify = verify
        self.legacy = legacy
        self.parsesig = parsesig
        self.hdronly = hdronly
        self.issrc = 0
        self.where = 0  # 0:lead 1:separator 2:sig 3:header 4:files
        self.idx = 0 # Current index
        self.hdr = {}
        self.hdrtype = {}

    def open(self):
        return 0

    def close(self):
        if self.cpiofd:
            self.cpiofd = None
        if self.cpio:
            self.cpio = None
        return 1

    def read(self):
        if self.fd == None:
            self.open()
        if self.fd == None:
            return (None, None)
        # Read/check leadata
        if self.where == 0:
            self.where = 1
            return self.readLead()
        # Separator
        if self.where == 1:
            self.readSig()
            # Shall we skip signature parsing/reading?
            if (self.verify or self.parsesig) and not self.hdronly:
                self.where = 2
            else:
                self.idx = self.hdrdata[0]+1
                self.where = 2
            return ("-", "")
        # Read/parse signature
        if self.where == 2:
            # Last index of sig? Switch to from sig to hdr
            if self.idx >= self.hdrdata[0]:
                self.readHdr()
                self.idx = 0
                self.where = 3
                return ("-", "")
            v = self.getHeaderByIndex(self.idx, self.hdrdata[3], self.hdrdata[4])
            self.idx += 1
            return (rpmsigtagname[v[0]], v[1])
        # Read/parse hdr
        if self.where == 3:
            # Last index of hdr? Switch to data files archive
            if self.idx >= self.hdrdata[0]:
                self.hdrdata = None
                self.hdr = {}
                self.hdrtype = {}
                self.cpiofd = gzip.GzipFile(fileobj=self.fd)
                self.cpio = CPIOFile(self.cpiofd)
                self.where = 4
                return ("-", "")
            v =  self.getHeaderByIndex(self.idx, self.hdrdata[3], self.hdrdata[4])
            self.idx += 1
            return (rpmtagname[v[0]], v[1])
        # Read/parse data files archive
        if self.where == 4:
            (filename, filedata, filerawdata) = self.cpio.getNextEntry()
            if filename != None:
                return (filename, filerawdata)
        return  ("EOF", "")

    def readLead(self):
        leaddata = self.fd.read(96)
        if leaddata[:4] != RPM_HEADER_LEAD_MAGIC:
            printError("%s: no rpm magic found" % self.source)
            return (None, None)
        if self.verify and not self.verifyLead(leaddata):
            return (None, None)
        return ("magic", leaddata[:4])

    def readSig(self):
        self.hdr = {}
        self.hdrtype = {}
        self.hdrdata = self.readIndex(8, 1)

    def readHdr(self):
        self.hdr = {}
        self.hdrtype = {}
        self.hdrdata = self.readIndex(1)

    def getHeaderByIndex(self, idx, indexdata, storedata):
        index = unpack("!4i", indexdata[idx*16:(idx+1)*16])
        tag = index[0]
        # ignore duplicate entries as long as they are identical
        if self.hdr.has_key(tag):
            if self.hdr[tag] != self.parseTag(index, storedata):
                printError("%s: tag %d included twice" % (self.source, tag))
        else: 
            self.hdr[tag] = self.parseTag(index, storedata)
            self.hdrtype[tag] = index[1]
        return (tag, self.hdr[tag])

    def verifyLead(self, leaddata):
        (magic, major, minor, rpmtype, arch, name, osnum, sigtype) = \
            unpack("!4scchh66shh16x", leaddata)
        ret = 1
        if major not in ('\x03', '\x04') or minor != '\x00' or \
            sigtype != 5 or rpmtype not in (0, 1):
            ret = 0
        if osnum not in (1, 255, 256):
            ret = 0
        name = name.rstrip('\x00')
        if self.legacy:
            if os.path.basename(self.source)[:len(name)] != name:
                ret = 0
        if not ret:
            printError("%s: wrong data in rpm lead" % self.source)
        return ret

    def readIndex(self, pad, issig=None):
        data = self.fd.read(16)
        if not len(data):
            return None
        (magic, indexNo, storeSize) = unpack("!8sii", data)
        if magic != "\x8e\xad\xe8\x01\x00\x00\x00\x00" or indexNo < 1:
            raiseFatal("%s: bad index magic" % self.source)
        fmt = self.fd.read(16 * indexNo)
        fmt2 = self.fd.read(storeSize)
        padfmt = ""
        if pad != 1:
            padfmt = self.fd.read((pad - (storeSize % pad)) % pad)
        if self.verify: 
            self.verifyIndex(fmt, fmt2, indexNo, storeSize, issig)
        return (indexNo, storeSize, data, fmt, fmt2, 16 + len(fmt) + \
            len(fmt2) + len(padfmt))

    def verifyIndex(self, fmt, fmt2, indexNo, storeSize, issig):
        checkSize = 0
        for i in xrange(0, indexNo * 16, 16):
            index = unpack("!iiii", fmt[i:i + 16])
            ttype = index[1]
            # alignment for some types of data
            if ttype == RPM_INT16:
                checkSize += (2 - (checkSize % 2)) % 2
            elif ttype == RPM_INT32:
                checkSize += (4 - (checkSize % 4)) % 4
            elif ttype == RPM_INT64:
                checkSize += (8 - (checkSize % 8)) % 8
            checkSize += self.verifyTag(index, fmt2, issig)
        if checkSize != storeSize:
            # XXX: add a check for very old rpm versions here, seems this
            # is triggered for a few RHL5.x rpm packages
            printError("%s: storeSize/checkSize is %d/%d" % (self.source, storeSize, checkSize))

    def verifyTag(self, index, fmt, issig):
        (tag, ttype, offset, count) = index
        if issig:
            if not rpmsigtag.has_key(tag):
                printError("%s: rpmsigtag has no tag %d" % (self.source, tag))
            else:
                t = rpmsigtag[tag]
                if t[1] != None and t[1] != ttype:
                    printError("%s: sigtag %d has wrong type %d" % (self.source, tag, ttype))
                if t[2] != None and t[2] != count:
                    printError("%s: sigtag %d has wrong count %d" % (self.source, tag, count))
                if (t[3] & 1) and self.legacy:
                    printError("%s: tag %d is marked legacy" % (self.source, tag))
                if self.issrc:
                    if (t[3] & 4):
                        printError("%s: tag %d should be for binary rpms" % (self.source, tag))
                else:
                    if (t[3] & 2):
                        printError("%s: tag %d should be for src rpms" % (self.source, tag))
        else:
            if not rpmtag.has_key(tag):
                printError("%s: rpmtag has no tag %d" % (self.source, tag))
            else:
                t = rpmtag[tag]
                if t[1] != None and t[1] != ttype:
                    if t[1] == RPM_ARGSTRING and (ttype == RPM_STRING or \
                        ttype == RPM_STRING_ARRAY):
                        pass    # special exception case
                    elif t[0] == rpmconstants.RPMTAG_GROUP and \
                        ttype == RPM_STRING: # XXX hardcoded exception
                        pass
                    else:
                        printError("%s: tag %d has wrong type %d" % (self.source, tag, ttype))
                if t[2] != None and t[2] != count:
                    printError("%s: tag %d has wrong count %d" % (self.source, tag, count))
                if (t[3] & 1) and self.legacy:
                    printError("%s: tag %d is marked legacy" % (self.source, tag))
                if self.issrc:
                    if (t[3] & 4):
                        printError("%s: tag %d should be for binary rpms" % (self.source, tag))
                else:
                    if (t[3] & 2):
                        printError("%s: tag %d should be for src rpms" % (self.source, tag))
        if count == 0:
            raiseFatal("%s: zero length tag" % self.source)
        if ttype < 1 or ttype > 9:
            raiseFatal("%s: unknown rpmtype %d" % (self.source, ttype))
        if ttype == RPM_INT32:
            count = count * 4
        elif ttype == RPM_STRING_ARRAY or \
            ttype == RPM_I18NSTRING:
            size = 0 
            for i in xrange(0, count):
                end = fmt.index('\x00', offset) + 1
                size += end - offset
                offset = end
            count = size 
        elif ttype == RPM_STRING:
            if count != 1:
                raiseFatal("%s: tag string count wrong" % self.source)
            count = fmt.index('\x00', offset) - offset + 1
        elif ttype == RPM_CHAR or ttype == RPM_INT8:
            pass
        elif ttype == RPM_INT16:
            count = count * 2
        elif ttype == RPM_INT64:
            count = count * 8
        elif ttype == RPM_BIN:
            pass
        else:
            raiseFatal("%s: unknown tag header" % self.source)
        return count

    def parseTag(self, index, fmt):
        (tag, ttype, offset, count) = index
        if ttype == RPM_INT32:
            return unpack("!%dI" % count, fmt[offset:offset + count * 4])
        elif ttype == RPM_STRING_ARRAY or ttype == RPM_I18NSTRING:
            data = []
            for i in xrange(0, count):
                end = fmt.index('\x00', offset)
                data.append(fmt[offset:end])
                offset = end + 1
            return data
        elif ttype == RPM_STRING:
            return fmt[offset:fmt.index('\x00', offset)]
        elif ttype == RPM_CHAR:
            return unpack("!%dc" % count, fmt[offset:offset + count])
        elif ttype == RPM_INT8:
            return unpack("!%dB" % count, fmt[offset:offset + count])
        elif ttype == RPM_INT16:
            return unpack("!%dH" % count, fmt[offset:offset + count * 2])
        elif ttype == RPM_INT64:
            return unpack("!%dQ" % count, fmt[offset:offset + count * 8])
        elif ttype == RPM_BIN:
            return fmt[offset:offset + count]
        raiseFatal("%s: unknown tag type: %d" % (self.source, ttype))
        return None

    def generateTag(self, tag, ttype, value):
        # Decided if we have to write out a list or a single element
        if isinstance(value, types.TupleType) or isinstance(value, types.ListType):
            count = len(value)
        else:
            count = 0
        # Normally we don't have strings. And strings always need to be '\x0'
        # terminated.
        isstring = 0
        if ttype == RPM_STRING or \
           ttype == RPM_STRING_ARRAY or\
           ttype == RPM_I18NSTRING: 
            format = "s"
            isstring = 1
        elif ttype == RPM_BIN:
            format = "s"
        elif ttype == RPM_CHAR:
            format = "c"
        elif ttype == RPM_INT8:
            format = "B"
        elif ttype == RPM_INT16:
            format = "H"
        elif ttype == RPM_INT32:
            format = "I"
        elif ttype == RPM_INT64:
            format = "Q"
        else:
            raiseFatal("%s: unknown tag header" % self.source)
        if count == 0:
            if format == "s":
                data = pack("!"+str(len(value)+isstring)+format, value)
            else:
                data = pack("!"+format, value)
        else:
            data = ""
            for i in xrange(0,count):
                if format == "s":
                    data += pack("!"+str(len(value[i])+isstring)+format, value[i])
                else:
                    data += pack("!"+format, value[i])
        # Fix counter. If it was a list, keep the counter.
        # If it was a single element, use 1 or if it is a RPM_BIN type the
        # length of the binary data.
        if count == 0:
            if ttype == RPM_BIN:
                count = len(value)
            else:
                count = 1
        return (count, data)

    def generateIndex(self, indexlist, store, pad):
        index = RPM_HEADER_INDEX_MAGIC
        index += pack("!ii", len(indexlist), len(store))
        (tag, ttype, offset, count) = indexlist.pop()
        index += pack("!iiii", tag, ttype, offset, count)
        for (tag, ttype, offset, count) in indexlist:
            index += pack("!iiii", tag, ttype, offset, count)
        align = (pad - (len(store) % pad)) % pad
        return (index, pack("%ds" % align, '\x00'))
            
    def alignTag(self, ttype, offset):
        if ttype == RPM_INT16:
            align = (2 - (offset % 2)) % 2
        elif ttype == RPM_INT32:
            align = (4 - (offset % 4)) % 4
        elif ttype == RPM_INT64:
            align = (8 - (offset % 8)) % 8
        else:
            align = 0
        return pack("%ds" % align, '\x00')

    def generateSig(self, header):
        store = ""
        offset = 0
        indexlist = []
        keys = rpmsigtag.keys()
        keys.sort()
        for tag in keys:
            if not isinstance(tag, types.IntType):
                continue
            # We need to handle tag 62 at the very end...
            if tag == 62:
                continue
            key = rpmsigtagname[tag]
            # Skip keys we don't have
            if not header.has_key(key):
                continue
            value = header[key]
            ttype = rpmsigtag[tag][1]
            # Convert back the RPM_ARGSTRING to RPM_STRING
            if ttype == RPM_ARGSTRING:
                ttype = RPM_STRING
            (count, data) = self.generateTag(tag, ttype, value)
            pad = self.alignTag(ttype, offset)
            offset += len(pad)
            indexlist.append((tag, ttype, offset, count))
            store += pad + data
            offset += len(data)
        # Handle tag 62 if we have it.
        tag = 62
        key = rpmsigtagname[tag]
        if header.has_key(key):
            value = header[key]
            ttype = rpmsigtag[tag][1]
            # Convert back the RPM_ARGSTRING to RPM_STRING
            if ttype == RPM_ARGSTRING:
                ttype = RPM_STRING
            (count, data) = self.generateTag(tag, ttype, value)
            pad = self.alignTag(ttype, offset)
            offset += len(pad)
            indexlist.append((tag, ttype, offset, count))
            store += pad + data
            offset += len(data)
        (index, pad) = self.generateIndex(indexlist, store, 8)
        return (index, store+pad)

    def generateHeader(self, header):
        store = ""
        indexlist = []
        offset = 0
        keys = rpmtag.keys()
        keys.sort()
        for tag in keys:
            if not isinstance(tag, types.IntType):
                continue
            # We need to handle tag 63 at the very end...
            if tag == 63:
                continue
            key = rpmtagname[tag]
            if not header.has_key(key):
                continue
            value = header[key]
            ttype = rpmtag[tag][1]
            # Convert back the RPM_ARGSTRING to RPM_STRING
            if ttype == RPM_ARGSTRING:
                ttype = RPM_STRING
            (count, data) = self.generateTag(tag, ttype, value)
            pad = self.alignTag(ttype, offset)
            offset += len(pad)
            indexlist.append((tag, ttype, offset, count))
            store += pad + data
            offset += len(data)
        # Handle tag 63 if we have it.
        tag = 63
        key = rpmtagname[tag]
        if header.has_key(key):
            value = header[key]
            ttype = rpmtag[tag][1]
            # Convert back the RPM_ARGSTRING to RPM_STRING
            if ttype == RPM_ARGSTRING:
                ttype = RPM_STRING
            (count, data) = self.generateTag(tag, ttype, value)
            pad = self.alignTag(ttype, offset)
            offset += len(pad)
            indexlist.append((tag, ttype, offset, count))
            store += pad + data
            offset += len(data)
        (index, pad) = self.generateIndex(indexlist, store, 1)
        return (index, store+pad)

    def write(self, data):
        if self.fd == None:
            self.open("w")
        if self.fd == None:
            return 0
        lead = pack("!4scchh66shh16x", RPM_HEADER_LEAD_MAGIC, '\x04', '\x00', 0, 1, data.getNEVR()[0:66], rpm_lead_arch[data["arch"]], 5)
        (sigindex, sigdata) = self.generateSig(data["signature"])
        (headerindex, headerdata) = self.generateHeader(data.data)
        self.fd.write(lead)
        self.fd.write(sigindex)
        self.fd.write(sigdata)
        self.fd.write(headerindex)
        self.fd.write(headerdata)
        return 1

    def writeHeader(self, data):
            return 0

    def writeData(self, data):
            return 0


class RpmDBIO(RpmIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmIO.__init__(self)


class RpmFtpIO(RpmIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmIO.__init__(self)


class RpmFileIO(RpmStreamIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmStreamIO.__init__(self, source, verify, legacy, parsesig, hdronly)
        self.issrc = 0
        if source[-8:] == ".src.rpm" or source[-10:] == ".nosrc.rpm":
            self.issrc = 1

    def openFile(self, mode="r"):
        if not self.fd:
            try:
                self.fd = open(self.source, mode)
            except:
                raiseFatal("%s: could not open file" % self.source)
#            if offset:
#                self.fd.seek(offset, 1)

    def closeFile(self):
        if self.fd != None:
            self.fd.close()
        self.fd = None

    def open(self, mode="r"):
        RpmStreamIO.open(self)
        self.openFile(mode)
        return 1

    def close(self):
        RpmStreamIO.close(self)
        self.closeFile()
        return 1


class RpmHttpIO(RpmIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmStreamIO.__init__(self, source, verify, legacy, parsesig, hdronly)

    def open(self):
        pass

    def open(self):
        pass


class RpmRepoIO(RpmIO):
    def __init__(self, source, verify=None, legacy=None, parsesig=None, hdronly=None):
        RpmIO.__init__(self)


def getRpmIOFactory(source, verify=None, legacy=None, parsesig=None, hdronly=None):
    if source[:4] == 'db:/':
        return RpmDBIO(source[4:], verify, legacy, parsesig, hdronly)
    elif source[:5] == 'ftp:/':
        return RpmFtpIO(source[5:], verify, legacy, parsesig, hdronly)
    elif source[:6] == 'file:/':
        return RpmFileIO(source[6:], verify, legacy, parsesig, hdronly)
    elif source[:6] == 'http:/':
        return RpmHttpIO(source[6:], verify, legacy, parsesig, hdronly)
    elif source[:6] == 'repo:/':
        return RpmRepoIO(source[6:], verify, legacy, parsesig, hdronly)
    else:
        return RpmFileIO(source, verify, legacy, parsesig, hdronly)
    return None

# vim:ts=4:sw=4:showmatch:expandtab