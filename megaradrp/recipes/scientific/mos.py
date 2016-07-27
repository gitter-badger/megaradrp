#
# Copyright 2011-2016 Universidad Complutense de Madrid
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

'''Calibration Recipes for Megara'''
from base import ImageRecipe
import logging

_logger = logging.getLogger('numina.recipes.megara')


class MOSImageRecipe(ImageRecipe):
    """Process MOS images."""

    def __init__(self):
        super(MOSImageRecipe, self).__init__()

    def run(self, rinput):

        _logger.info('starting MOS reduction')

        result = super(MOSImageRecipe,self).run(rinput)

        return self.create_result(final=result[0], target=result[1], sky=result[2])