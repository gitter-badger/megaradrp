#
# Copyright 2015-2017 Universidad Complutense de Madrid
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

""" Twilight fiber flat Calibration Recipes for Megara"""

from __future__ import division, print_function


import numpy
from astropy.io import fits

from numina.core import Product, Requirement
from numina.core.products import DataFrameType

import megaradrp.requirements as reqs
from megaradrp.core.processing import apextract_tracemap
from megaradrp.core.recipe import MegaraBaseRecipe
from megaradrp.requirements import MasterBiasRequirement
from megaradrp.products import WavelengthCalibration
from megaradrp.products import TraceMap
from megaradrp.types import MasterTwilightFlat

# Flat 2D
from megaradrp.processing.combine import basic_processing_with_combination
from numina.array import combine
# Create RSS
from megaradrp.processing.aperture import ApertureExtractor
from megaradrp.processing.wavecalibration import WavelengthCalibrator
from megaradrp.processing.fiberflat import Splitter, FlipLR


class TwilightFiberFlatRecipe(MegaraBaseRecipe):

    master_bias = reqs.MasterBiasRequirement()
    master_dark = reqs.MasterDarkRequirement()
    master_bpm = reqs.MasterBPMRequirement()
    master_slitflat = reqs.MasterSlitFlatRequirement()
    tracemap = reqs.MasterTraceMapRequirement()
    # master_weights = Requirement(MasterWeights, 'Set of files with extraction weights')
    wlcalib = Requirement(WavelengthCalibration, 'Wavelength calibration table')
    # Products

    reduced_frame = Product(DataFrameType)
    reduced_rss = Product(DataFrameType)
    master_twilight_flat = Product(MasterTwilightFlat)

    def process_flat2d(self, rinput):
        flow = self.init_filters(rinput, rinput.obresult.configuration)
        final_image = basic_processing_with_combination(rinput, flow, method=combine.median)
        hdr = final_image[0].header
        self.set_base_headers(hdr)
        return final_image

    def run(self, rinput):
        # Basic processing

        self.logger.info('twilight fiber flat reduction started')

        img = self.process_flat2d(rinput)
        splitter1 = Splitter()
        calibrator_aper = ApertureExtractor(rinput.tracemap, self.datamodel)
        splitter2 = Splitter()
        calibrator_wl = WavelengthCalibrator(rinput.wlcalib, self.datamodel)
        flipcor = FlipLR()

        img = splitter1(img)
        flat2d = splitter1.out # Copy before extraction
        img = calibrator_aper(img)
        img = splitter2(img)
        rss_base = splitter2.out # Copy before el calibration
        self.logger.debug('Flip RSS left-rigtht, before WL calibration')
        img = flipcor.run(img)
        # Calibrate in WL
        rss_wl = calibrator_wl(img)

        # Measure values in final
        start = 1900
        end = 2100
        self.logger.info('doing mean between columns %d-%d', start, end)
        colapse = rss_wl[:, start:end].mean(axis=1)

        normalized = numpy.tile(colapse[:, numpy.newaxis], 4096)

        template_header = flat2d[0].header
        master_t_hdu = fits.PrimaryHDU(normalized, header=template_header)
        master_t = fits.HDUList([master_t_hdu])

        self.logger.info('twilight fiber flat reduction ended')
        result = self.create_result(reduced_frame=flat2d, reduced_rss=rss_wl,
                                    master_twilight_flat=master_t)

        return result


class TwilightFiberFlatRecipeALT(MegaraBaseRecipe):

    master_bias = MasterBiasRequirement()
    tracemap = Requirement(TraceMap, 'Trace information of the Apertures')
    wlcalib = Requirement(WavelengthCalibration, 'Wavelength calibration table')
    # Products

    reduced_frame = Product(DataFrameType)
    reduced_rss = Product(DataFrameType)
    master_twilight_flat = Product(MasterTwilightFlat)

    def __init__(self):
        super(TwilightFiberFlatRecipeALT, self).__init__(
            version="0.1.0"
        )

    def run(self, rinput):
        # Basic processing
        self.logger.info('twilight fiber flat reduction started')

        parameters = self.get_parameters(rinput)

        reduced = self.bias_process_common(rinput.obresult, parameters)

        self.logger.info('extract fibers')
        rssdata = apextract_tracemap(reduced[0].data, rinput.tracemap)

        # FIXME: we are ignoring here all the possible bad pixels
        # and WL distortion when doing the normalization
        # rssdata /= rssdata.mean() #Originally uncomment
        template_header = reduced[0].header
        rsshdu = fits.PrimaryHDU(rssdata, header=template_header)
        rss = fits.HDUList([rsshdu])

        self.logger.info('extraction completed')

        self.logger.info('resampling spectra')
        final, wcsdata = self.resample_rss_flux(rsshdu.data, self.get_wlcalib(rinput.wlcalib))
        # This value was ~0.4% and now is 4e-6 %
        # (abs(final.sum()-hdu_t.data.sum())/hdu_t.data.sum()*100)

        # Measure values in final
        start = 200
        end = 2100
        self.logger.info('doing mean between columns %d-%d', start, end)
        colapse = final[:,start:end].mean(axis=1)

        normalized = numpy.tile(colapse[:, numpy.newaxis], 4096)

        master_t_hdu = fits.PrimaryHDU(normalized, header=template_header)
        header_list = self.getHeaderList([reduced, rinput.obresult.images[0].open()])
        master_t = fits.HDUList([master_t_hdu]+header_list)


        self.logger.info('twilight fiber flat reduction ended')
        result = self.create_result(reduced_frame=reduced, reduced_rss=rss,
                                    master_twilight_flat=master_t)
        return result
