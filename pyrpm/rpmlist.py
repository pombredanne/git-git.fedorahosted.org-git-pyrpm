#!/usr/bin/python
#
# Copyright (C) 2004, 2005 Red Hat, Inc.
# Author: Thomas Woerner, Karel Zak
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

from hashlist import HashList
from config import rpmconfig
from functions import buildarchtranslate, printWarning, pkgCompare, \
     archCompat, archDuplicate
from base import OP_INSTALL, OP_UPDATE, OP_ERASE, OP_FRESHEN

class RpmList:
    OK = 1
    ALREADY_INSTALLED = -1
    OLD_PACKAGE = -2
    NOT_INSTALLED = -3
    UPDATE_FAILED = -4
    ALREADY_ADDED = -5
    ARCH_INCOMPAT = -6
    # ----

    def __init__(self, installed, operation):
        self.clear()
        self.__len__ = self.list.__len__
        for r in installed:
            self._install(r)
            if not self.installed.has_key(r["name"]):
                self.installed[r["name"]] = [ ]
            self.installed[r["name"]].append(r)
        self.operation = operation
    # ----

    def clear(self):
        self.list = HashList()
        self.installed = HashList()
        self.appended = [ ]
    # ----

    def __getitem__(self, i):
        return self.list[i][1] # return rpm list
    # ----

    def append(self, pkg):
        if self.operation == OP_INSTALL:
            ret = self._install(pkg)
            if ret != self.OK:  return ret
        elif self.operation == OP_UPDATE:
            ret = self._update(pkg)
            if ret != self.OK:  return ret
        elif self.operation == OP_FRESHEN:
            # pkg in self.installed
            if not self.installed.has_key(pkg["name"]):
                return self.NOT_INSTALLED
            found = 0
            for r in self.installed[pkg["name"]]:
                if pkg["arch"] == r["arch"] or \
                       buildarchtranslate[pkg["arch"]] == \
                       buildarchtranslate[r["arch"]]:
                    found = 1
                    break
            if found == 0:
                return self.NOT_INSTALLED
            ret = self._update(pkg)
            if ret != self.OK:  return ret
        else: # self.operation == OP_ERASE:
            if self._erase(pkg) != 1:
                return self.NOT_INSTALLED
            self._pkgErase(pkg)
        self.appended.append(pkg)
        return self.OK
    # ----

    def _install(self, pkg):
        key = pkg["name"]
        if self.installed.has_key(key):
            for r in self.installed[key]:
                if r == pkg or \
                   (r.getNEVR() == pkg.getNEVR() and \
                    (pkg["arch"] == r["arch"] or \
                     buildarchtranslate[pkg["arch"]] == \
                     buildarchtranslate[r["arch"]])):
                    printWarning(1, "%s: %s is already installed" % \
                                 (pkg.getNEVRA(), r.getNEVRA()))
                    return self.ALREADY_INSTALLED
        if self.list.has_key(key):
            if pkg in self.list[key]:
                printWarning(1, "%s was already added" % pkg.getNEVRA())
                return self.ALREADY_ADDED
        else:
            self.list[key] = [ ]
        self.list[key].append(pkg)

        return self.OK
    # ----

    def _update(self, pkg):
        key = pkg["name"]

        updates = [ ]
        if self.list.has_key(key):
            rpms = self.list[pkg["name"]]
            
            for r in rpms:
                ret = pkgCompare(r, pkg)
                if ret > 0:
                    if rpmconfig.oldpackage == 0:
                        if self.isInstalled(r):
                            msg = "%s: A newer package is already installed"
                        else:
                            msg = "%s: A newer package was already added"
                        printWarning(1, msg % pkg.getNEVRA())
                        return self.OLD_PACKAGE
                    else:
                        # old package: simulate a new package
                        ret = -1
                if ret < 0: # old_ver < new_ver
                    if rpmconfig.exactarch == 1 and \
                           pkg["arch"] != r["arch"] and \
                           archDuplicate(pkg["arch"], r["arch"]):
                        printWarning(1, "%s does not match arch %s." % \
                                     (pkg.getNEVRA(), r["arch"]))
                        return self.ARCH_INCOMPAT
                    if archDuplicate(pkg["arch"], r["arch"]):
                        updates.append(r)
                elif ret == 0: # old_ver == new_ver
                    if rpmconfig.exactarch == 1 and \
                           pkg["arch"] != r["arch"] and \
                           archDuplicate(pkg["arch"], r["arch"]):
                        printWarning(1, "%s does not match arch %s." % \
                                     (pkg.getNEVRA(), r["arch"]))
                        return self.ARCH_INCOMPAT

                    if archCompat(pkg["arch"], r["arch"]):
                        if self.isInstalled(r):
                            printWarning(1, "%s is already installed" % \
                                         pkg.getNEVRA())
                            return self.ALREADY_INSTALLED
                        else:
                            printWarning(1, "%s was already added" % \
                                         pkg.getNEVRA())
                            return self.ALREADY_ADDED
                    else:
                        if archDuplicate(pkg["arch"], r["arch"]):
                            updates.append(r)

        ret = self._install(pkg)
        if ret != self.OK:  return ret

        for r in updates:
            if self.isInstalled(r):
                msg = "%s was already installed, replacing with %s"
            else:
                msg = "%s was already added, replacing with %s"
            printWarning(1, msg % (r.getNEVRA(), pkg.getNEVRA()))
            if self._pkgUpdate(pkg, r) != self.OK:
                return self.UPDATE_FAILED

        return self.OK
    # ----

    def _erase(self, pkg):
        key = pkg["name"]
        if not self.list.has_key(key) or pkg not in self.list[key]:
            return self.NOT_INSTALLED
        self.list[key].remove(pkg)
        if len(self.list[key]) == 0:
            del self.list[key]
        if pkg in self.appended:
            self.appended.remove(pkg)
        return 1
    # ----

    def _pkgUpdate(self, pkg, update_pkg):
        return self._erase(update_pkg)
    # ----

    def _pkgErase(self, pkg):
        return self.OK
    # ----

    def isInstalled(self, pkg):
        if self.installed.has_key(pkg["name"]) and \
               pkg in self.installed[pkg["name"]]:
            return 1
        return 0
    # ----

    def getList(self):
        l = [ ]
        for i in xrange(len(self)):
            l.extend(self[i])
        return l
    # ----

    def p(self):
        for i in xrange(len(self)):
            rlist = self[i]
            for r in rlist:
                print "\t%s" % r.getNEVRA()

# vim:ts=4:sw=4:showmatch:expandtab
