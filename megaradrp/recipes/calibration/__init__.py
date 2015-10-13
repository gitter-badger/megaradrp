#
# Copyright 2011-2014 Universidad Complutense de Madrid
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

from .base import DarkRecipe
from .base import PseudoFluxCalibrationRecipe
from .flat import TraceMapRecipe, TwilightFiberFlatRecipe
from .flat import FiberFlatRecipe
from .base import LCB_IFU_StdStarRecipe, FiberMOS_StdStarRecipe
from .base import SensitivityFromStdStarRecipe, S_And_E_FromStdStarsRecipe
from .base import BadPixelsMaskRecipe, LinearityTestRecipe

from megaradrp.recipes.calibration.bias import BiasRecipe
