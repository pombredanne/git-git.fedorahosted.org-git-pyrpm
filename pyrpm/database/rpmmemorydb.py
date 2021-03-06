 #
# Copyright (C) 2004, 2005 Red Hat, Inc.
# Authors: Phil Knirsch, Thomas Woerner, Florian La Roche
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

import os, bsddb
from pyrpm.base import *
import memorydb, rpmdb

class RpmMemoryDB(memorydb.RpmMemoryDB, rpmdb.RpmDB):
    """Standard RPM database storage in BSD db."""

    def __init__(self, config, source, buildroot=''):
        memorydb.RpmMemoryDB.__init__(self, config, source, buildroot)
        rpmdb.RpmDB.__init__(self, config, source, buildroot)

        self.tags = {}
        for tag in config.resolvertags:
            if tag.startswith("file"):
                continue
            self.tags[tag] = None
        del self.obsoletes_list # set in rpmdb.RpmDB.__init__
                                # but needs to be removed to get auto created

    open = rpmdb.RpmDB.open
    close = rpmdb.RpmDB.close


    def read(self):
        # Never fails, attempts to recover as much as possible
        if self.is_read:
            return 1
        self.is_read = 1
        if not os.path.isdir(self.path):
            return 1
        try:
            db = bsddb.hashopen(os.path.join(self.path, "Packages"), "r")
        except bsddb.error:
            return 1
        for key in db.keys():
            pkg = self.readRpm(key, db, self.tags)
            if pkg is not None:
                memorydb.RpmMemoryDB.addPkg(self, pkg)
        return 1

    def addPkg(self, pkg):
        result = rpmdb.RpmDB._addPkg(self, pkg)
        if result:
            memorydb.RpmMemoryDB.addPkg(self, pkg)
        return result

    def removePkg(self, pkg):
        result = rpmdb.RpmDB._removePkg(self, pkg)
        if result:
            memorydb.RpmMemoryDB.removePkg(self, pkg)
        return result

# vim:ts=4:sw=4:showmatch:expandtab
