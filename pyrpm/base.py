#
# Copyright (C) 2004, 2005 Red Hat, Inc.
# Author: Phil Knirsch, Thomas Woerner, Florian La Roche
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
#

import os.path
from struct import unpack

class RpmFileInfo:
    def __init__(self, config, filename, inode, mode, uid, gid, mtime, filesize,
                 dev, rdev, md5sum, linktos, flags, verifyflags, filecolor):
        self.config = config            # FIXME: write-only
        self.filename = filename        # Usually real name, but can be modified
        self.inode = inode            # rpm header limited to int32; write-only
        self.mode = mode                # Standard stat file modes
        self.uid = uid                  # int32 uid instead of name as in cpio
        self.gid = gid                  # int32 gid instead of name as in cpio
        self.mtime = mtime
        self.filesize = filesize        # rpm header limited to int32
        self.dev = dev                  # FIXME: write-only
        self.rdev = rdev                # rpm header limited to int16
        self.md5sum = md5sum            # Uncoverted md5sum from header
        self.linktos = linktos          # Target file in case of symlink
        self.flags = flags              # RPMFILE_*
        self.verifyflags = verifyflags  # FIXME: write-only
        self.filecolor = filecolor      # FIXME: write-only

    def getHardLinkID(self):
        """Return a string integer representing
        (self.md5sum, self.inode, self.dev)."""
    
        return self.md5sum+":"+str(self.inode*65536+self.dev)


class FilenamesList:
    """A mapping from filenames to RpmPackages."""

    def __init__(self, config):
        self.config = config            # FIXME: write-only
        self.clear()

    def clear(self):
        """Clear the mapping."""
        
        self.path = { } # dirname => { basename => RpmPackage }

    def addPkg(self, pkg):
        """Add all files from RpmPackage pkg to self."""

        if pkg["basenames"] == None:
            return
        for i in xrange (len(pkg["basenames"])):
            dirname = pkg["dirnames"][pkg["dirindexes"][i]]

            if not self.path.has_key(dirname):
                self.path[dirname] = { }

            basename = pkg["basenames"][i]
            if not self.path[dirname].has_key(basename):
                self.path[dirname][basename] = [ ]
            self.path[dirname][basename].append(pkg)

    def removePkg(self, pkg):
        """Remove all files from RpmPackage pkg from self."""

        if pkg["basenames"] == None:
            return
        for i in xrange (len(pkg["basenames"])):
            dirname = pkg["dirnames"][pkg["dirindexes"][i]]

            if not self.path.has_key(dirname):
                continue

            basename = pkg["basenames"][i]
            if self.path[dirname].has_key(basename):
                self.path[dirname][basename].remove(pkg)

            if len(self.path[dirname][basename]) == 0:
                del self.path[dirname][basename]

    def search(self, name):
        """Return list of packages providing file with name.

        The list may point to internal structures of FilenamesList and may be
        changed by calls to addPkg() and removePkg()."""
        
        l = [ ]
        dirname = os.path.dirname(name)
        if len(dirname) > 0 and dirname[-1] != "/":
            dirname += "/"
        basename = os.path.basename(name)
        if self.path.has_key(dirname) and \
               self.path[dirname].has_key(basename):
            l = self.path[dirname][basename]
        return l

class RpmIndexData:
    # Class method, self is NOT used.
    def getKey(item):
        """Extracts the tag/sigtag key from a given item and return it"""

        if item[0] == "S":
            item = item[1:]
        if item[-2] == ",":
            item = item[:-2]
        return item
    getKey = staticmethod(getKey)

    def __init__(self, config, index=None, storelen=None, sindex=None,
                 sstorelen=None):
        self.config = config
        self.sigidx = []        # Signature index list
        self.sighash = {}       # Signature tag hash
        self.hdridx = []        # Header index list
        self.hdrhash = {}       # Header tag hash
        if index != None:
            self.__createHashIdx(index, self.hdridx, self.hdrhash, storelen)
        if sindex != None:
            self.__createHashIdx(sindex, self.sigidx, self.sighash, sstorelen)

    def __createHashIdx(self, index, idx, hash, slen):
        """Generate our internal index and hash lists needed to optimaly
        perform the requests
        """ 

        lenlist = []
        # First extract all indexes from the given binary index.
        # There are 2 internal lists for each index:
        # the idx list contains all indexes as lists of 5 integers. The first 4
        # values are the original index values, the 5th is the actual computed
        # length of the datasegement for this index.
        for i in xrange(len(index)/16):
            entry = unpack("!4I", index[i*16:(i+1)*16])
            idx.append(entry)
            tag    = entry[0]
            offset = entry[2]
            if not hash.has_key(tag):
                hash[tag] = []
            hash[tag].append(i)
            lenlist.append((offset, i))
        # Now we calculate the sizes for the index entries using a sorted list
        # of the offsets with proper indexes.
        lenlist.sort()
        t2 = [0]*len(lenlist)
        for i in xrange(len(lenlist)-1):
            t2[lenlist[i][1]] = lenlist[i+1][0] - lenlist[i][0]
        t2[lenlist[-1][1]] = slen-lenlist[-1][0]
        # Extend the original indexes with the computed lengths
        for i in xrange(len(t2)):
            idx[i] = list(idx[i])
            idx[i].append(t2[i])

    def getIndex(self, item):
        # Find out if user wants a different occurence than the 1st
        if item[-2] == ",":
            key = item[:-2]
            pos = int(item[-1])
        else:
            key = item
            pos = 0
        # Check from which tagspace the data should be get (sig or normal
        # header)
        if item[0] == "S":
            tag = rpmsigtag[key[1:]][0]
            tidx = self.sigidx
            thash = self.sighash
        else:
            tag = rpmtag[key][0]
            tidx = self.hdridx
            thash = self.hdrhash
        # No such tag -> return None
        if not thash.has_key(tag):
            return None
        return tidx[thash[tag][pos]]

    def has_key(self, item):
        key = RpmIndexData.getKey(item)
        if item[0] == "S":
            return rpmsigtag.has_key(key) and \
                   self.sighash.has_key(rpmsigtag[key][0])
        else:
            return rpmtag.has_key(key) and self.hdrhash.has_key(rpmtag[key][0])

    def keys(self):
        klist = []
        counthash = {}
        for index in self.sigidx:
            item = "S"+rpmsigtagname[index[0]]
            if not counthash.has_key(item):
                counthash[item] = 0
            else:
                counthash[item] += 1
                item += ","+str(counthash[item])
            klist.append(item)
        for index in self.hdridx:  
            item = rpmtagname[index[0]]
            if not counthash.has_key(item):
                counthash[item] = 0
            else:
                counthash[item] += 1
                item += ","+str(counthash[item])
            klist.append(item)
        return klist

    def parseTag(self, index, store):
        """Parse value of tag with index from data in store.

        Return tag value.  Raise ValueError on invalid data."""

        (tag, ttype, offset, count, len) = index
        offset = 0
        try:
            if ttype == RPM_INT32:
                return unpack("!%dI" % count, store[:count * 4])
            elif ttype == RPM_STRING_ARRAY or ttype == RPM_I18NSTRING:
                data = []
                for _ in xrange(0, count):
                    end = store.index('\x00', offset)
                    data.append(store[offset:end])
                    offset = end + 1
                return data
            elif ttype == RPM_STRING:
                return store[offset:store.index('\x00')]
            elif ttype == RPM_CHAR:
                return unpack("!%dc" % count, store[:count])
            elif ttype == RPM_INT8:
                return unpack("!%dB" % count, store[:count])
            elif ttype == RPM_INT16:
                return unpack("!%dH" % count, store[:count*2])
            elif ttype == RPM_INT64:
                return unpack("!%dQ" % count, store[:count*8])
            elif ttype == RPM_BIN:
                return store[:count]
            raise ValueError, "unknown tag type: %d" % ttype
        except struct.error:
            raise ValueError, "Invalid header data"


# RPM Constants - based from rpmlib.h and elsewhere

# rpm tag types
#RPM_NULL = 0
RPM_CHAR = 1
RPM_INT8 = 2
RPM_INT16 = 3
RPM_INT32 = 4
RPM_INT64 = 5 # currently unused
RPM_STRING = 6
RPM_BIN = 7
RPM_STRING_ARRAY = 8
RPM_I18NSTRING = 9
# new type internal to this tool:
# RPM_STRING_ARRAY for app + params, otherwise a single RPM_STRING
RPM_ARGSTRING = 12

# RPMSENSEFLAGS
RPMSENSE_ANY        = 0
RPMSENSE_SERIAL     = (1 << 0)  # legacy
RPMSENSE_LESS       = (1 << 1)
RPMSENSE_GREATER    = (1 << 2)
RPMSENSE_EQUAL      = (1 << 3)
RPMSENSE_PROVIDES   = (1 << 4) # only used internally by builds
RPMSENSE_CONFLICTS  = (1 << 5) # only used internally by builds
RPMSENSE_PREREQ     = (1 << 6)     # @todo Legacy.
RPMSENSE_OBSOLETES  = (1 << 7) # only used internally by builds
RPMSENSE_INTERP     = (1 << 8)     # Interpreter used by scriptlet.
RPMSENSE_SCRIPT_PRE = ((1 << 9)|RPMSENSE_PREREQ) # %pre dependency.
RPMSENSE_SCRIPT_POST = ((1 << 10)|RPMSENSE_PREREQ) # %post dependency.
RPMSENSE_SCRIPT_PREUN = ((1 << 11)|RPMSENSE_PREREQ) # %preun dependency.
RPMSENSE_SCRIPT_POSTUN = ((1 << 12)|RPMSENSE_PREREQ) # %postun dependency.
RPMSENSE_SCRIPT_VERIFY = (1 << 13) # %verify dependency.
RPMSENSE_FIND_REQUIRES = (1 << 14) # find-requires generated dependency.
RPMSENSE_FIND_PROVIDES = (1 << 15) # find-provides generated dependency.
RPMSENSE_TRIGGERIN  = (1 << 16)    # %triggerin dependency.
RPMSENSE_TRIGGERUN  = (1 << 17)    # %triggerun dependency.
RPMSENSE_TRIGGERPOSTUN = (1 << 18) # %triggerpostun dependency.
RPMSENSE_MISSINGOK  = (1 << 19)    # suggests/enhances/recommends hint.
RPMSENSE_SCRIPT_PREP = (1 << 20)   # %prep build dependency.
RPMSENSE_SCRIPT_BUILD = (1 << 21)  # %build build dependency.
RPMSENSE_SCRIPT_INSTALL = (1 << 22)# %install build dependency.
RPMSENSE_SCRIPT_CLEAN = (1 << 23)  # %clean build dependency.
RPMSENSE_RPMLIB     = ((1 << 24) | RPMSENSE_PREREQ) # rpmlib(feature) dep.
RPMSENSE_TRIGGERPREIN = (1 << 25)  # @todo Implement %triggerprein.
RPMSENSE_KEYRING    = (1 << 26)
RPMSENSE_PATCHES    = (1 << 27)
RPMSENSE_CONFIG     = (1 << 28)

RPMSENSE_SENSEMASK  = 15 # Mask to get senses: serial, less, greater, equal.

RPMSENSE_TRIGGER = (RPMSENSE_TRIGGERIN | RPMSENSE_TRIGGERUN \
    | RPMSENSE_TRIGGERPOSTUN)

_ALL_REQUIRES_MASK  = (RPMSENSE_INTERP | RPMSENSE_SCRIPT_PRE \
    | RPMSENSE_SCRIPT_POST | RPMSENSE_SCRIPT_PREUN | RPMSENSE_SCRIPT_POSTUN \
    | RPMSENSE_SCRIPT_VERIFY | RPMSENSE_FIND_REQUIRES | RPMSENSE_SCRIPT_PREP \
    | RPMSENSE_SCRIPT_BUILD | RPMSENSE_SCRIPT_INSTALL | RPMSENSE_SCRIPT_CLEAN \
    | RPMSENSE_RPMLIB | RPMSENSE_KEYRING)

def _notpre(x):
    return (x & ~RPMSENSE_PREREQ)

_INSTALL_ONLY_MASK = _notpre(RPMSENSE_SCRIPT_PRE | RPMSENSE_SCRIPT_POST \
    | RPMSENSE_RPMLIB | RPMSENSE_KEYRING)
_ERASE_ONLY_MASK   = _notpre(RPMSENSE_SCRIPT_PREUN | RPMSENSE_SCRIPT_POSTUN)

def isLegacyPreReq(x):
    return (x & _ALL_REQUIRES_MASK) == RPMSENSE_PREREQ
def isInstallPreReq(x):
    return (x & _INSTALL_ONLY_MASK) != 0
def isErasePreReq(x):
    return (x & _ERASE_ONLY_MASK) != 0

# RPM file attributes
RPMFILE_NONE        = 0
RPMFILE_CONFIG      = (1 <<  0)    # from %%config
RPMFILE_DOC         = (1 <<  1)    # from %%doc
RPMFILE_ICON        = (1 <<  2)    # from %%donotuse.
RPMFILE_MISSINGOK   = (1 <<  3)    # from %%config(missingok)
RPMFILE_NOREPLACE   = (1 <<  4)    # from %%config(noreplace)
RPMFILE_SPECFILE    = (1 <<  5)    # .spec file in source rpm
RPMFILE_GHOST       = (1 <<  6)    # from %%ghost
RPMFILE_LICENSE     = (1 <<  7)    # from %%license
RPMFILE_README      = (1 <<  8)    # from %%readme
RPMFILE_EXCLUDE     = (1 <<  9)    # from %%exclude, internal
RPMFILE_UNPATCHED   = (1 << 10)    # placeholder (SuSE)
RPMFILE_PUBKEY      = (1 << 11)    # from %%pubkey
RPMFILE_POLICY      = (1 << 12)    # from %%policy


# RPM file verify flags
RPMVERIFY_NONE      = 0
RPMVERIFY_MD5       = (1 << 0)     # from %verify(md5)
RPMVERIFY_FILESIZE  = (1 << 1)     # from %verify(size)
RPMVERIFY_LINKTO    = (1 << 2)     # from %verify(link)
RPMVERIFY_USER      = (1 << 3)     # from %verify(user)
RPMVERIFY_GROUP     = (1 << 4)     # from %verify(group)
RPMVERIFY_MTIME     = (1 << 5)     # from %verify(mtime)
RPMVERIFY_MODE      = (1 << 6)     # from %verify(mode)
RPMVERIFY_RDEV      = (1 << 7)     # from %verify(rdev)


OP_INSTALL = "install"
OP_UPDATE = "update"
OP_ERASE = "erase"
OP_FRESHEN = "freshen"


# List of all rpm tags we care about. We mark older tags which are
# not anymore in newer rpm packages (Fedora Core development tree) as
# "legacy".
# tagname: (tag, type, how-many, flags:legacy=1,src-only=2,bin-only=4, storeflags:never=0,onread=1,immediate=2)
rpmtag = {
    # basic info
    "name": (1000, RPM_STRING, None, 0, 2),
    "epoch": (1003, RPM_INT32, 1, 0, 2),
    "version": (1001, RPM_STRING, None, 0, 2),
    "release": (1002, RPM_STRING, None, 0, 2),
    "arch": (1022, RPM_STRING, None, 0, 2),

    # dependencies: provides, requires, obsoletes, conflicts
    "providename": (1047, RPM_STRING_ARRAY, None, 0, 0),
    "provideflags": (1112, RPM_INT32, None, 0, 0),
    "provideversion": (1113, RPM_STRING_ARRAY, None, 0, 0),
    "requirename": (1049, RPM_STRING_ARRAY, None, 0, 0),
    "requireflags": (1048, RPM_INT32, None, 0, 0),
    "requireversion": (1050, RPM_STRING_ARRAY, None, 0, 0),
    "obsoletename": (1090, RPM_STRING_ARRAY, None, 4, 0),
    "obsoleteflags": (1114, RPM_INT32, None, 4, 0),
    "obsoleteversion": (1115, RPM_STRING_ARRAY, None, 4, 0),
    "conflictname": (1054, RPM_STRING_ARRAY, None, 0, 0),
    "conflictflags": (1053, RPM_INT32, None, 0, 0),
    "conflictversion": (1055, RPM_STRING_ARRAY, None, 0, 0),

    # triggers
    "triggername": (1066, RPM_STRING_ARRAY, None, 4, 0),
    "triggerflags": (1068, RPM_INT32, None, 4, 0),
    "triggerversion": (1067, RPM_STRING_ARRAY, None, 4, 0),
    "triggerscripts": (1065, RPM_STRING_ARRAY, None, 4, 0),
    "triggerscriptprog": (1092, RPM_STRING_ARRAY, None, 4, 0),
    "triggerindex": (1069, RPM_INT32, None, 4, 0),

    # scripts
    "prein": (1023, RPM_STRING, None, 4, 0),
    "preinprog": (1085, RPM_ARGSTRING, None, 4, 0),
    "postin": (1024, RPM_STRING, None, 4, 0),
    "postinprog": (1086, RPM_ARGSTRING, None, 4, 0),
    "preun": (1025, RPM_STRING, None, 4, 0),
    "preunprog": (1087, RPM_ARGSTRING, None, 4, 0),
    "postun": (1026, RPM_STRING, None, 4, 0),
    "postunprog": (1088, RPM_ARGSTRING, None, 4, 0),
    "verifyscript": (1079, RPM_STRING, None, 4, 0),
    "verifyscriptprog": (1091, RPM_ARGSTRING, None, 4, 0),

    # addon information:
    "i18ntable": (100, RPM_STRING_ARRAY, None, 0, 0), # list of available langs
    "summary": (1004, RPM_I18NSTRING, None, 0, 0),
    "description": (1005, RPM_I18NSTRING, None, 0, 0),
    "url": (1020, RPM_STRING, None, 0, 0),
    "license": (1014, RPM_STRING, None, 0, 0),
    "rpmversion": (1064, RPM_STRING, None, 0, 0),
    "sourcerpm": (1044, RPM_STRING, None, 4, 0),
    "changelogtime": (1080, RPM_INT32, None, 0, 0),
    "changelogname": (1081, RPM_STRING_ARRAY, None, 0, 0),
    "changelogtext": (1082, RPM_STRING_ARRAY, None, 0, 0),
    "prefixes": (1098, RPM_STRING_ARRAY, None, 4, 0), # relocatable rpm packages
    "optflags": (1122, RPM_STRING, None, 4, 0), # optimization flags for gcc
    "pubkeys": (266, RPM_STRING_ARRAY, None, 4, 0),
    "sourcepkgid": (1146, RPM_BIN, 16, 4, 0), # md5 from srpm (header+payload)
    "immutable": (63, RPM_BIN, 16, 0, 0), # content of this tag is unclear
    # less important information:
    "buildtime": (1006, RPM_INT32, 1, 0, 0), # time of rpm build
    "buildhost": (1007, RPM_STRING, None, 0, 0), # hostname where rpm was built
    "cookie": (1094, RPM_STRING, None, 0, 0), # build host and time
    # ignored now, successor is comps.xml
    # Code allows hardcoded exception to also have type RPM_STRING
    # for RPMTAG_GROUP==1016.
    "group": (1016, RPM_I18NSTRING, None, 0, 0),
    "size": (1009, RPM_INT32, 1, 0, 0),                # sum of all file sizes
    "distribution": (1010, RPM_STRING, None, 0, 0),
    "vendor": (1011, RPM_STRING, None, 0, 0),
    "packager": (1015, RPM_STRING, None, 0, 0),
    "os": (1021, RPM_STRING, None, 0, 0),              # always "linux"
    "payloadformat": (1124, RPM_STRING, None, 0, 0),   # "cpio"
    "payloadcompressor": (1125, RPM_STRING, None, 0, 0),# "gzip" or "bzip2"
    "payloadflags": (1126, RPM_STRING, None, 0, 0),    # "9"
    "rhnplatform": (1131, RPM_STRING, None, 4, 0),     # == arch
    "platform": (1132, RPM_STRING, None, 0, 0),

    # rpm source packages:
    "source": (1018, RPM_STRING_ARRAY, None, 2, 0),
    "patch": (1019, RPM_STRING_ARRAY, None, 2, 0),
    "buildarchs": (1089, RPM_STRING_ARRAY, None, 2, 0),
    "excludearch": (1059, RPM_STRING_ARRAY, None, 2, 0),
    "exclusivearch": (1061, RPM_STRING_ARRAY, None, 2, 0),
    "exclusiveos": (1062, RPM_STRING_ARRAY, None, 2, 0), # ['Linux'] or ['linux']

    # information about files
    "dirindexes": (1116, RPM_INT32, None, 0, 0),
    "dirnames": (1118, RPM_STRING_ARRAY, None, 0, 0),
    "basenames": (1117, RPM_STRING_ARRAY, None, 0, 0),
    "fileusername": (1039, RPM_STRING_ARRAY, None, 0, 0),
    "filegroupname": (1040, RPM_STRING_ARRAY, None, 0, 0),
    "filemodes": (1030, RPM_INT16, None, 0, 0),
    "filemtimes": (1034, RPM_INT32, None, 0, 0),
    "filedevices": (1095, RPM_INT32, None, 0, 0),
    "fileinodes": (1096, RPM_INT32, None, 0, 0),
    "filesizes": (1028, RPM_INT32, None, 0, 0),
    "filemd5s": (1035, RPM_STRING_ARRAY, None, 0, 0),
    "filerdevs": (1033, RPM_INT16, None, 0, 0),
    "filelinktos": (1036, RPM_STRING_ARRAY, None, 0, 0),
    "fileflags": (1037, RPM_INT32, None, 0, 0),
    "fileverifyflags": (1045, RPM_INT32, None, 0, 0),
    "fileclass": (1141, RPM_INT32, None, 0, 0),
    "filelangs": (1097, RPM_STRING_ARRAY, None, 0, 0),
    "filecolors": (1140, RPM_INT32, None, 0, 0),
    "filedependsx": (1143, RPM_INT32, None, 0, 0),
    "filedependsn": (1144, RPM_INT32, None, 0, 0),
    "classdict": (1142, RPM_STRING_ARRAY, None, 0, 0),
    "dependsdict": (1145, RPM_INT32, None, 0, 0),

    # SELinux stuff, needed for some FC4-extras packages
    "policies": (1150, RPM_STRING_ARRAY, None, 0, 0),

    # tags not in Fedora Core development trees anymore:
    "filecontexts": (1147, RPM_STRING_ARRAY, None, 1, 0), # selinux filecontexts
    "capability": (1105, RPM_INT32, None, 1, 0),
    "xpm": (1013, RPM_BIN, None, 1, 0),
    "gif": (1012, RPM_BIN, None, 1, 0),
    # bogus RHL5.2 data in XFree86-libs, ash, pdksh
    "verifyscript2": (15, RPM_STRING, None, 1, 0),
    "nosource": (1051, RPM_INT32, None, 1, 0),
    "nopatch": (1052, RPM_INT32, None, 1, 0),
    "disturl": (1123, RPM_STRING, None, 1, 0),
    "oldfilenames": (1027, RPM_STRING_ARRAY, None, 1, 0),
    "triggerin": (1100, RPM_STRING, None, 5, 0),
    "triggerun": (1101, RPM_STRING, None, 5, 0),
    "triggerpostun": (1102, RPM_STRING, None, 5, 0),

    # install information
    "install_size_in_sig": (257, RPM_INT32, 1, 0, 0),
    "install_md5": (261, RPM_BIN, 16, 0, 0),
    "install_gpg": (262, RPM_BIN, None, 0, 0),
    "install_badsha1_1": (264, RPM_STRING, None, 1, 0),
    "install_badsha1_2": (265, RPM_STRING, None, 1, 0),
    "install_dsaheader": (267, RPM_BIN, 16, 0, 0),
    "install_sha1header": (269, RPM_STRING, None, 0, 0),
    "installtime": (1008, RPM_INT32, None, 0, 0),
    "filestates": (1029, RPM_CHAR, None, 0, 0),
    "archivesize": (1046, RPM_INT32, 1, 1, 0),
    "instprefixes": (1099, RPM_STRING_ARRAY, None, 0, 0),
    "installcolor": (1127, RPM_INT32, None, 0, 0),
    "installtid": (1128, RPM_INT32, None, 0, 0)
}
rpmtagname = {}
# Add a reverse mapping for all tags and a new tag -> name mapping.
for key in rpmtag.keys():
    v = rpmtag[key]
    rpmtag[v[0]] = v
    rpmtagname[v[0]] = key
del v
del key

# Required tags in a header.
rpmtagrequired = []
for key in ["name", "version", "release", "arch"]:
    rpmtagrequired.append(rpmtag[key][0])
del key

# Info within the sig header.
rpmsigtag = {
    # size of gpg/dsaheader sums differ between 64/65(contains '\n')
    "dsaheader": (267, RPM_BIN, None, 0, 0),
    "gpg": (1005, RPM_BIN, None, 0, 0),
    "header_signatures": (62, RPM_BIN, 16, 0, 0), # content of this tag is unclear
    "payloadsize": (1007, RPM_INT32, 1, 0, 0),
    "size_in_sig": (1000, RPM_INT32, 1, 0, 0),
    "sha1header": (269, RPM_STRING, None, 0, 0),
    "md5": (1004, RPM_BIN, 16, 0, 0),
    # legacy entries in older rpm packages:
    "pgp": (1002, RPM_BIN, None, 1, 0),
    "badsha1_1": (264, RPM_STRING, None, 1, 0),
    "badsha1_2": (265, RPM_STRING, None, 1, 0)
}
# Add a reverse mapping for all tags and a new tag -> name mapping
rpmsigtagname = {}
for key in rpmsigtag.keys():
    v = rpmsigtag[key]
    rpmsigtag[v[0]] = v
    rpmsigtagname[v[0]] = key
del key
del v

# Required tags in a signature header.
rpmsigtagrequired = []
for key in ["md5"]:
    rpmsigtagrequired.append(rpmsigtag[key][0])
del key


# check arch names against this list
possible_archs = {'noarch':1, 'i386':1, 'i486':1, 'i586':1, 'i686':1,
    'athlon':1, 'pentium3':1, 'pentium4':1, 'x86_64':1, 'ia32e':1, 'ia64':1,
    'alpha':1, 'axp':1, 'sparc':1, 'sparc64':1, 's390':1, 's390x':1, 'ia64':1,
    'ppc':1, 'ppc64':1, 'ppc64iseries':1, 'ppc64pseries':1, 'ppcpseries':1,
    'ppciseries':1, 'ppcmac':1, 'ppc8260':1, 'm68k':1,
    'arm':1, 'armv4l':1, 'mips':1, 'mipseb':1, 'mipsel':1, 'hppa':1, 'sh':1 }


# arch => compatible archs, best match first
arch_compats = {
"noarch" : ["noarch"],

"alphaev67" : ["alphaev6", "alphapca56", "alphaev56", "alphaev5", "alpha",
    "axp", "noarch"],
"alphaev6" : ["alphapca56", "alphaev56", "alphaev5", "alpha", "axp", "noarch"],
"alphapca56" : ["alphaev56", "alphaev5", "alpha", "axp", "noarch"],
"alphaev56" : ["alphaev5", "alpha", "axp", "noarch"],
"alphaev5" : ["alpha", "axp", "noarch"],
"alpha" : ["axp", "noarch"],

"athlon" : ["i686", "i586", "i486", "i386", "noarch"],
"i686" : ["i586", "i486", "i386", "noarch"],
"i586" : ["i486", "i386", "noarch"],
"i486" : ["i386", "noarch"],
"i386" : ["noarch"],

"osfmach3_i686": ["i686", "osfmach3_i586", "i586", "osfmach3_i486", "i486",
    "osfmach3_i386", "i486", "i386", "noarch"],
"osfmach3_i586": ["i586", "osfmach3_i486", "i486", "osfmach3_i386", "i486",
    "i386", "noarch"],
"osfmach3_i486": ["i486", "osfmach3_i386", "i486", "i386", "noarch"],
"osfmach3_i386": ["i486", "i386", "noarch"],

"osfmach3_ppc" : ["ppc", "rs6000", "noarch"],
"powerpc" : ["ppc", "rs6000", "noarch"],
"powerppc" : ["ppc", "rs6000", "noarch"],
"ppc8260" : ["ppc", "rs6000", "noarch"],
"ppc8560" : ["ppc", "rs6000", "noarch"],
"ppc32dy4" : ["ppc", "rs6000", "noarch"],
"ppciseries" : ["ppc", "rs6000", "noarch"],
"ppcpseries" : ["ppc", "rs6000", "noarch"],
"ppc64" : ["ppc", "rs6000", "noarch"],
"ppc" : ["rs6000", "noarch"],
"rs6000" : ["noarch"],
"ppc64pseries" : ["ppc64", "ppc", "rs6000", "noarch"],
"ppc64iseries" : ["ppc64", "ppc", "rs6000", "noarch"],

"sun4c" : ["sparc", "noarch"],
"sun4d" : ["sparc", "noarch"],
"sun4m" : ["sparc", "noarch"],
"sun4u" : ["sparc64", "sparcv9", "sparc", "noarch"],
"sparc64" : ["sparcv9", "sparc", "noarch"],
"sparcv9" : ["sparc", "noarch"],
"sparcv8" : ["sparc", "noarch"],
"sparc" : ["noarch"],

"mips" : ["noarch"],
"mipsel" : ["noarch"],

"hppa2.0" : ["hppa1.2", "hppa1.1", "hppa1.0", "parisc", "noarch"],
"hppa1.2" : ["hppa1.1", "hppa1.0", "parisc", "noarch"],
"hppa1.1" : ["hppa1.0", "parisc", "noarch"],
"hppa1.0" : ["parisc", "noarch"],
"parisc" : ["noarch"],

"armv4b" : ["noarch"],
"armv4l" : ["armv3l", "noarch"],
"armv3l" : ["noarch"],

"atarist" : ["m68kmint", "noarch"],
"atariste" : ["m68kmint", "noarch"],
"ataritt" : ["m68kmint", "noarch"],
"falcon" : ["m68kmint", "noarch"],
"atariclone" : ["m68kmint", "noarch"],
"milan" : ["m68kmint", "noarch"],
"hades" : ["m68kmint", "noarch"],

"i370" : ["noarch"],
"s390" : ["noarch"],
"s390x" : ["s390", "noarch"],

"ia64" : ["noarch"],

"x86_64" : ["amd64", "athlon", "i686", "i586", "i486", "i386", "noarch"],
"amd64" : ["x86_64", "athlon", "i686", "i586", "i486", "i386", "noarch"],
"ia32e" : ["x86_64", "athlon", "i686", "i586", "i486", "i386", "noarch"]
}

# Buildarchtranslate table for multilib stuff: arch => base arch
buildarchtranslate = {
"osfmach3_i686" : "i386",
"osfmach3_i586" : "i386",
"osfmach3_i486" : "i386",
"osfmach3_i386" : "i386",

"athlon" : "i386",
"pentium4" : "i386",
"pentium3" : "i386",
"i686" : "i386",
"i586" : "i386",
"i486" : "i386",
"i386" : "i386",

"alphaev5" : "alpha",
"alphaev56" : "alpha",
"alphapca56" : "alpha",
"alphaev6" : "alpha",
"alphaev67" : "alpha",
"alpha" : "alpha",

"sun4c" : "sparc",
"sun4d" : "sparc",
"sun4m" : "sparc",
"sparcv8" : "sparc",
"sparcv9" : "sparc",
"sun4u" : "sparc64",
"sparc" : "sparc",
"sparc64" : "sparc64",

"osfmach3_ppc" : "ppc",
"powerpc" : "ppc",
"powerppc" : "ppc",
"ppc8260" : "ppc",
"ppc8560" : "ppc",
"ppc32dy4" : "ppc",
"ppciseries" : "ppc",
"ppcpseries" : "ppc",
"ppc64pseries" : "ppc64",
"ppc64iseries" : "ppc64",
"ppc" : "ppc",
"ppc64" : "ppc64",

"atarist" : "m68kmint",
"atariste" : "m68kmint",
"ataritt" : "m68kmint",
"falcon" : "m68kmint",
"atariclone" : "m68kmint",
"milan" : "m68kmint",
"hades" : "m68kmint",
"m68kmint" : "m68kmint",

"s390" : "s390",
"s390x" : "s390x",

"ia64" : "ia64",

"amd64" : "x86_64",
"ia32e" : "x86_64",
"x86_64" : "x86_64",

"noarch" : "noarch"
}


# Some special magics for binary rpms
RPM_HEADER_LEAD_MAGIC = '\xed\xab\xee\xdb'
RPM_HEADER_INDEX_MAGIC = "\x8e\xad\xe8\x01\x00\x00\x00\x00"

# rpm binary lead arch values
rpm_lead_arch = {
"alphaev67" : 2,
"alphaev6" : 2,
"alphapca56" : 2,
"alphaev56" : 2,
"alphaev5" : 2,
"alpha" : 2,
"athlon" : 1,
"i686" : 1,
"i586" : 1,
"i486" : 1,
"i386" : 1,
"osfmach3_i686": 1,
"osfmach3_i586": 1,
"osfmach3_i486": 1,
"osfmach3_i386": 1,
"osfmach3_ppc" : 5,
"powerpc" : 5,
"powerppc" : 5,
"ppc8260" : 5,
"ppc8560" : 5,
"ppc32dy4" : 5,
"ppciseries" : 5,
"ppcpseries" : 5,
"ppc64" : 5,
"ppc" : 5,
"rs6000" : 5,
"ppc64pseries" : 5,
"ppc64iseries" : 5,
"sun4c" : 3,
"sun4d" : 3,
"sun4m" : 3,
"sun4u" : 3,
"sparc64" : 3,
"sparcv9" : 3,
"sparcv8" : 3,
"sparc" : 3,
"mips" : 4,
"mipsel" : 4,
"hppa2.0" : 0,
"hppa1.2" : 0,
"hppa1.1" : 0,
"hppa1.0" : 0,
"parisc" : 0,
"armv4b" : 0,
"armv4l" : 0,
"armv3l" : 0,
"atarist" : 6,
"atariste" : 6,
"ataritt" : 6,
"falcon" : 6,
"atariclone" : 6,
"milan" : 6,
"hades" : 6,
"i370" : 0,
"s390" : 0,
"s390x" : 0,
"ia64" : 1,
"x86_64" : 1,
"amd64" : 1,
"ia32e" : 1,
"noarch" : 255
}

# vim:ts=4:sw=4:showmatch:expandtab
