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

"""Calibration Recipes for Megara"""


import numpy.polynomial.polynomial as nppol
from scipy.interpolate import interp1d
from astropy.io import fits
from astropy import wcs
from numina.core import Product, Requirement
from numina.core.requirements import ObservationResultRequirement

from megaradrp.core.recipe import MegaraBaseRecipe
import megaradrp.requirements as reqs
from megaradrp.types import MasterFiberFlat
from megaradrp.types import ProcessedRSS, ProcessedFrame


class PseudoFluxCalibrationRecipe(MegaraBaseRecipe):
    obresult = ObservationResultRequirement()
    master_bias = reqs.MasterBiasRequirement()
    master_fiberflat = reqs.MasterFiberFlatRequirement()
    traces = reqs.MasterTraceMapRequirement()
    reference_spectrum = Requirement(MasterFiberFlat, 'Reference spectrum')

    calibration = Product(ProcessedFrame)
    calibration_rss = Product(ProcessedRSS)

    def run(self, rinput):
        self.logger.info('starting pseudo flux calibration')

        parameters = self.get_parameters(rinput)
        reduced = self.bias_process_common(rinput.obresult, parameters)

        # hdr['NUMTYP'] = ('SCIENCE_TARGET', 'Data product type')

        # FIXME: hardcoded calibration
        # Polynomial that translates pixels to wl
        self.logger.warning('using hardcoded LR-U spectral calibration')
        wlcal = [7.12175997e-10, -9.36387541e-06, 2.13624855e-01,
                 3.64665269e+03]
        plin = nppol.Polynomial(wlcal[::-1])
        wl_n_r = plin(range(1, reduced[0].data.shape[1] + 1))  # Non-regular WL

        self.logger.info('resampling reference spectrum')

        with rinput.reference_spectrum.open() as hdul:
            # Needs resampling
            data = hdul[0].data
            w_ref = wcs.WCS(hdul[0].header)
            # FIXME: Hardcoded values
            # because we do not have WL calibration
            pix = range(1, len(data) + 1)
            wl = w_ref.wcs_pix2world(pix, 1)
            # The 0 mean 0-based
            si = interp1d(wl, data)
            # Reference spectrum evaluated in the irregular WL grid
            final = si(wl_n_r)

        sens_data = final / reduced[0].data
        hdu_sens = fits.PrimaryHDU(sens_data, header=reduced[0].header)
        header_list = self.getHeaderList([reduced, rinput.obresult.images[0].open()])
        hdu_sens = fits.HDUList([hdu_sens] + header_list)

        self.logger.info('pseudo flux calibration reduction ended')

        result = self.create_result(calibration=hdu_sens,
                                    calibration_rss=reduced)
        return result
