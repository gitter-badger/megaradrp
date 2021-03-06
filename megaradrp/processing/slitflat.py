#
# Copyright 2016 Universidad Complutense de Madrid
#
# This file is part of Megara DRP
#
# Megara DRP is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Megara DRP is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Megara DRP.  If not, see <http://www.gnu.org/licenses/>.
#


import logging
import datetime

from .fiberflat import CommonFlatCorrector

_logger = logging.getLogger(__name__)


class SlitFlatCorrector(CommonFlatCorrector):
    """A Node that corrects a frame from slit flat."""

    def __init__(self, slitflat, datamodel=None, calibid='calibid-unknown',
                 dtype='float32'):

        super(SlitFlatCorrector, self).__init__(slitflat, datamodel, calibid, dtype)
        self.flattag = 'slitflat'

    def header_update(self, hdr, imgid):
        hdr['NUM-SLTF'] = self.calibid
        hdr['history'] = 'Slit flat correction {}'.format(imgid)
        hdr['history'] = 'Slit flat correction time {}'.format(datetime.datetime.utcnow().isoformat())
