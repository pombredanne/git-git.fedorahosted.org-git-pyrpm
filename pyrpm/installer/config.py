#
# Copyright (C) 2005,2006 Red Hat, Inc.
# Author: Thomas Woerner <twoerner@redhat.com>
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

from pyrpm.logger import Logger, log
from pyrpm.config import rpmconfig

# file logging object
flog = Logger()
flog.delInfoLogging("*", flog.stderr)
flog.delDebugLogging("*", flog.stderr)
flog.delInfoLogging("*", flog.stdout)
flog.delDebugLogging("*", flog.stdout)

# vim:ts=4:sw=4:showmatch:expandtab
