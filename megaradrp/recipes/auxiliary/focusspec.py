#
# Copyright 2016-2017 Universidad Complutense de Madrid
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

"""Focus Spectrograph Recipe for Megara"""

from __future__ import division, print_function


import numpy
import numpy.polynomial.polynomial as polynomial
from scipy.spatial import cKDTree
import astropy.io.fits as fits

from numina.array import combine
from numina.core import Requirement, Parameter
from numina.core.dataholders import Product
from numina.core.products import ArrayType
from numina.core.requirements import ObservationResultRequirement
from numina.exceptions import RecipeError
import numina.array.utils
import numina.array.fwhm as fmod
import numina.core.validator
from numina.array.stats import robust_std as sigmaG
from numina.array.peaks.peakdet import find_peaks_indexes, refine_peaks

from megaradrp.core.recipe import MegaraBaseRecipe
from megaradrp.products import WavelengthCalibration
from megaradrp.types import JSONstorage, ProcessedFrame
import megaradrp.requirements as reqs
from megaradrp.processing.combine import basic_processing_with_combination_frames
from megaradrp.processing.aperture import ApertureExtractor
from megaradrp.instrument import vph_thr_arc


class FocusSpectrographRecipe(MegaraBaseRecipe):
    """Process Focus images and find best focus."""

    # Requirements
    obresult = ObservationResultRequirement()
    master_bias = reqs.MasterBiasRequirement()
    master_dark = reqs.MasterDarkRequirement()
    master_bpm = reqs.MasterBPMRequirement()
    tracemap = reqs.MasterTraceMapRequirement()

    wlcalib = Requirement(WavelengthCalibration,
                          'Wavelength calibration table')
    nfibers = Parameter(10, "The results are sampled every nfibers")
    # Products
    focus_table = Product(ArrayType)
    focus_image = Product(ProcessedFrame)
    focus_wavelength = Product(JSONstorage)

    @numina.core.validator.validate
    def run(self, rinput):
        # Basic processing
        self.logger.info('start focus spectrograph')

        obresult = rinput.obresult

        flow = self.init_filters(rinput, obresult.configuration)

        current_vph = obresult.tags['vph']
        current_insmode = obresult.tags['insmode']

        if current_insmode in vph_thr_arc and current_vph in vph_thr_arc[current_insmode]:
            flux_limit = vph_thr_arc[current_insmode][current_vph].get('flux_limit', 200000)
            self.logger.info('flux_limit for %s is %4.2f', current_vph, flux_limit)
        else:
            flux_limit = 40000
            self.logger.info('flux limit not defined for %s, using %4.2f', current_vph, flux_limit)

        image_groups = {}
        self.logger.info('group images by focus')

        for idx, frame in enumerate(obresult.frames):
            with frame.open() as img:
                focus_val = img[0].header['focus']
                if focus_val not in image_groups:
                    self.logger.debug('new focus %s', focus_val)
                    image_groups[focus_val] = []
                self.logger.debug('image %s in group %s', img, focus_val)
                image_groups[focus_val].append(frame)

        if len(image_groups) < 2:
            raise RecipeError('We have only {} different focus'.format(len(image_groups)))

        # Loop only over fibers with WL calibration
        valid_traces = [fibsol.fibid for fibsol in rinput.wlcalib.contents]
        # valid_traces = [aper.fibid for aper in rinput.tracemap.contents if aper.valid]
        # every tenth fiber
        nfibers = rinput.nfibers
        valid_traces = valid_traces[::nfibers]

        ever = {}
        for focus, frames in image_groups.items():
            self.logger.info('processing focus %s', focus)

            try:
                img = basic_processing_with_combination_frames(frames, flow, method=combine.median, errors=False)
                calibrator_aper = ApertureExtractor(rinput.tracemap, self.datamodel)

                self.save_intermediate_img(img, 'focus2d-%s.fits' % (focus,))
                img1d = calibrator_aper(img)
                self.save_intermediate_img(img1d, 'focus1d-%s.fits' % (focus,))

                self.logger.info('find lines and compute FWHM')
                lines_rss_fwhm = self.run_on_image(img1d, rinput.tracemap, flux_limit, valid_traces=valid_traces)
                ever[focus] = lines_rss_fwhm

            except ValueError:
                self.logger.info('focus %s cannot be processed', focus)

        self.logger.info('pair lines in images')
        line_fibers = self.filter_lines(ever)

        focus_wavelength = self.generate_focus_wl(ever, rinput.wlcalib)

        self.logger.info('fit FWHM of lines')
        final = self.reorder_and_fit(line_fibers, sorted(image_groups.keys()))

        focus_median = numpy.median(final[:, 2])
        self.logger.info('median focus value is %5.2f', focus_median)

        self.logger.info('generate focus image')
        image = self.generate_image(final)
        focus_image_hdu = fits.PrimaryHDU(image)
        focus_image = fits.HDUList([focus_image_hdu])

        self.logger.info('end focus spectrograph')
        return self.create_result(focus_table=final, focus_image=focus_image,
                                  focus_wavelength=focus_wavelength)

    def run_on_image(self, img, tracemap, flux_limit=40000, valid_traces=None):
        """Extract spectra, find peaks and compute FWHM."""

        rssdata = img[0].data

        if valid_traces:
            valid_traces_s = set(valid_traces) # use set for fast membership
            valid_apers = [aper for aper in tracemap.contents if aper.valid and aper.fibid in valid_traces_s]
        else:
            valid_apers = [aper for aper in tracemap.contents if aper.valid]

        nwinwidth = 5
        times_sigma = 50.0
        lwidth = 20
        fpeaks = {}

        for aper in valid_apers:
            fibid = aper.fibid
            idx = fibid - 1
            row = rssdata[idx, :]

            the_pol = aper.polynomial

            # FIXME: using here a different peak routine than in arc
            # find peaks
            threshold = numpy.median(row) + times_sigma * sigmaG(row)

            ipeaks_int1 = find_peaks_indexes(row, nwinwidth, threshold)
            # filter by flux
            self.logger.info('Filtering peaks over %5.0f', flux_limit)
            ipeaks_vals = row[ipeaks_int1]
            mask = ipeaks_vals < flux_limit
            ipeaks_int = ipeaks_int1[mask]
            self.logger.debug('LEN (ipeaks_int): %s', len(ipeaks_int))
            self.logger.debug('ipeaks_int: %s', ipeaks_int)
            ipeaks_float = refine_peaks(row, ipeaks_int, nwinwidth)[0]

            # self.pintarGrafica(refine_peaks(row, ipeaks_int, nwinwidth)[0] - refinePeaks_spectrum(row, ipeaks_int, nwinwidth))

            fpeaks[fibid] = []
            for peak, peak_f in zip(ipeaks_int, ipeaks_float):
                try:
                    sl = numina.array.utils.slice_create(peak, lwidth)
                    rel_peak = peak - sl.start
                    qslit = row[sl]
                    peak_val, fwhm = fmod.compute_fwhm_1d_simple(qslit, rel_peak)
                    peak_on_trace = the_pol(peak)
                    fpeaks[fibid].append((peak_f, peak_on_trace, fwhm))
                except ValueError as error:
                    self.logger.warning('Error %s computing FWHM in fiber %d', error, fibid)
                except IndexError as error:
                    self.logger.warning('Error %s computing FWHM in fiber %d', error, fibid)
            self.logger.debug('found %d peaks in fiber %d', len(fpeaks[fibid]), fibid)
        return fpeaks

    def generate_image(self, final):
        # FIXME: hardcoded sizes
        voronoi_points = numpy.array(final[:, [0, 1]])
        x = numpy.arange(2048 * 2)
        y = numpy.arange(2056 * 2)

        test_points = numpy.transpose(
            [numpy.tile(x, len(y)), numpy.repeat(y, len(x))])

        voronoi_kdtree = cKDTree(voronoi_points)

        test_point_dist, test_point_regions = voronoi_kdtree.query(test_points, k=1)
        final_image = test_point_regions.reshape((4112, 4096)).astype('float64')
        final_image[:, :] = final[final_image[:, :].astype('int32'), 2]
        return final_image

    def generate_focus_wl(self, all_measures, wlcalib):


        self.logger.info('start result generation')

        result = {}

        wlfib = {}
        for s in wlcalib.contents:
            wlfib[s.fibid] = s.solution

        for focus, image in all_measures.items():
            cresult = {}
            result[focus] = cresult
            for fiber, value in image.items():
                cresult[fiber] = []
                for arco in value:
                    try:
                        # FIXME: hardcoded sizes
                        x = 2048 * 2 - arco[0]
                        res = polynomial.polyval(x, wlfib[fiber].coeff)
                        cresult[fiber].append([arco[0], arco[1], arco[2], res])
                    except KeyError:
                        self.logger.warning("Fiber %d hasn't WL calibration, skipping", fiber)

        self.logger.info('end result generation')

        return result

    def pintarGrafica(self, diferencia_final):
        if False:
            import matplotlib.pyplot as plt

            fig = plt.figure(1)
            ax = fig.add_subplot(111)

            ejeX = numpy.arange(len(diferencia_final))
            ax.plot(ejeX, diferencia_final, label="0")
            # lgd = ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=4,
            #                 mode="expand")
            lgd = ax.legend(bbox_to_anchor=(0., 1.02, 1., .102),
                            loc='upper center', ncol=4, mode="expand",
                            borderaxespad=0.)
            handles, labels = ax.get_legend_handles_labels()

            fig.savefig('diferencia.eps', format='eps', dpi=1500,
                        bbox_extra_artists=(lgd,), bbox_inches='tight')
            plt.draw()
            plt.show()

    def filter_lines(self, all_measures, maxdis=2.0):
        """Match lines between different images """

        values = sorted(all_measures.keys())
        ntotal = len(values)
        center = ntotal // 2
        center_focus = values[center]
        base = all_measures[center_focus]
        self.logger.debug('use image #%d as reference, focus=%s', center, center_focus)
        line_fibers = {}

        self.logger.debug('matching lines up to %3.1f pixels', maxdis)
        for fiberid in base:
            self.logger.debug('Using %d fiber in reference image', fiberid)
            ref = numpy.array(base[fiberid])
            if ref.size == 0:
                self.logger.debug('Reference fiber has no lines, skip')
                continue

            self.logger.debug('Positions are %s', ref)
            outref = len(ref)
            savelines = {}
            line_fibers[fiberid] = savelines
            for i in range(outref):
                savelines[i] = {}
                savelines[i]['basedata'] = {}
                savelines[i]['centers'] = []
            self.logger.debug('Create kd-tree in fiber %d', fiberid)
            kdtree = cKDTree(ref[:, :2])
            for i in range(ntotal):
                if i == center:
                    for j in range(outref):
                        savelines[j]['basedata']['coordinates'] = tuple(
                            ref[j, :2])
                        savelines[j]['centers'].append(ref[j, 2])
                    continue
                self.logger.debug('Matching lines in fiber %d in image # %d', fiberid, i)
                comp = numpy.array(all_measures[values[i]][fiberid])

                if comp.size == 0:
                    self.logger.debug('No lines in fiber %d in image # %d', fiberid, i)
                    continue
                else:
                    self.logger.debug('Using %d lines in fiber %d in image # %d', comp.size, fiberid, i)

                qdis, qidx = kdtree.query(comp[:, :2],
                                          distance_upper_bound=maxdis)
                for compidx, lidx in enumerate(qidx):
                    if lidx < outref:
                        savelines[lidx]['centers'].append(comp[compidx, 2])

            remove_groups = []

            for ir in savelines:
                if len(savelines[ir]['centers']) != ntotal:
                    remove_groups.append(ir)

            for ir in remove_groups:
                self.logger.debug('remove group of lines %d in fiber %d', ir,
                              fiberid)
                del savelines[ir]

        return line_fibers

    def reorder_and_fit(self, line_fibers, focii):
        """Fit all the values of FWHM to a 2nd degree polynomial and return minimum."""

        l = sum(len(value) for key, value in line_fibers.items())
        self.logger.debug('there are %d groups of lines to fit', l)
        ally = numpy.zeros((len(focii), l))
        final = numpy.zeros((l, 3))
        self.logger.debug('focci are %s', focii)
        l = 0
        for i in line_fibers:
            for j in line_fibers[i]:
                ally[:, l] = line_fibers[i][j]['centers']
                final[l, :2] = line_fibers[i][j]['basedata']['coordinates']
                l += 1

        self.logger.debug('line widths are %s', ally)
        try:
            res = numpy.polyfit(focii, ally, deg=2)
            self.logger.debug('fitting to deg 2 polynomial, done')
            best = -res[1] / (2 * res[0])
            final[:, 2] = best
        except ValueError as error:
            self.logger.warning("Error in fitting: %s", error)
            final[:, 2] = 0.0

        return final
