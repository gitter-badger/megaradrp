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

"""Base scientidic recipe for MEGARA"""


from astropy.io import fits
import numpy as np

from numina.core.requirements import ObservationResultRequirement, Requirement
from numina.flow import SerialFlow
from numina.array import combine

from megaradrp.core.recipe import MegaraBaseRecipe
from megaradrp.products import WavelengthCalibration
import megaradrp.requirements as reqs
from megaradrp.processing.combine import basic_processing_with_combination

from megaradrp.processing.aperture import ApertureExtractor
from megaradrp.processing.wavecalibration import WavelengthCalibrator
from megaradrp.processing.fiberflat import Splitter, FlipLR, FiberFlatCorrector


class ImageRecipe(MegaraBaseRecipe):
    """Base Image."""

    # Requirements  
    obresult = ObservationResultRequirement()
    master_bias = reqs.MasterBiasRequirement()
    master_dark = reqs.MasterDarkRequirement()
    master_bpm = reqs.MasterBPMRequirement()
    master_slitflat = reqs.MasterSlitFlatRequirement()
    wlcalib = Requirement(WavelengthCalibration, 'Wavelength calibration table')
    # master_weights = Requirement(MasterWeights, 'Set of files')
    master_fiberflat = reqs.MasterFiberFlatRequirement()
    master_twilight = reqs.MasterTwilightRequirement()
    tracemap = reqs.MasterTraceMapRequirement()

    def base_run(self, rinput):

        # 2D reduction
        flow1 = self.init_filters(rinput, rinput.obresult.configuration)
        img = basic_processing_with_combination(rinput, flow1, method=combine.median)
        hdr = img[0].header
        self.set_base_headers(hdr)

        # 1D, extraction, Wl calibration, Flat fielding
        reduced2d, reduced_rss = self.run_reduction_1d(
            img,
            rinput.tracemap,
            rinput.wlcalib,
            rinput.master_fiberflat
        )

        return reduced2d, reduced_rss

    def run_reduction_1d(self, img, tracemap, wlcalib, fiberflat):
        # 1D, extraction, Wl calibration, Flat fielding

        splitter1 = Splitter()
        calibrator_aper = ApertureExtractor(tracemap, self.datamodel)
        calibrator_wl = WavelengthCalibrator(wlcalib, self.datamodel)
        flipcor = FlipLR()
        calibrator_flat = FiberFlatCorrector(fiberflat.open(), self.datamodel)

        flow2 = SerialFlow([splitter1, calibrator_aper, flipcor, calibrator_wl, calibrator_flat])

        reduced_rss =  flow2(img)
        reduced2d = splitter1.out
        return reduced2d, reduced_rss

    def run_sky_subtraction(self, img):
        import numpy

        # Sky subtraction
        self.logger.info('obtain fiber information')
        sky_img = copy_img(img)
        final_img = copy_img(img)
        fiberconf = self.datamodel.get_fiberconf(sky_img)
        # Sky fibers
        self.logger.debug('sky fibers are: %s', fiberconf.sky_fibers(valid_only=True))
        # Create empty sky_data
        target_data = img[0].data

        target_map = img['WLMAP'].data
        sky_data = numpy.zeros_like(img[0].data)
        sky_map = numpy.zeros_like(img['WLMAP'].data)
        sky_img[0].data = sky_data

        for fibid in fiberconf.sky_fibers(valid_only=True):
            rowid = fibid - 1
            sky_data[rowid] = target_data[rowid]
            sky_map[rowid] = target_map[rowid]
            if False:
                import matplotlib.pyplot as plt
                plt.plot(sky_data[rowid])
                plt.title("%d" % fibid)
                plt.show()
        # Sum
        coldata = sky_data.sum(axis=0)
        colsum = sky_map.sum(axis=0)

        # Divide only where map is > 0
        mask = colsum > 0
        avg_sky = numpy.zeros_like(coldata)
        avg_sky[mask] = coldata[mask] / colsum[mask]

        # This should be done only on valid fibers
        # The information of which fiber is valid
        # is in the tracemap, not in the header
        for fibid in fiberconf.valid_fibers():
            rowid = fibid - 1
            final_img[0].data[rowid, mask] = img[0].data[rowid, mask] - avg_sky[mask]

        return final_img, img, sky_img

    def get_wcallib(self, lambda1, lambda2, fibras, traces, rss, neigh_info, grid):

        # Take a look at == []
        indices = []
        wlcalib = []
        for elem in traces:
            if elem['aperture']['function']['coefficients']:
                wlcalib.append(elem['aperture']['function']['coefficients'])
                if len(indices)==0:
                    indices.append(0)
                else:
                    indices.append(indices[-1])
            else:
                indices.append(indices[-1]+1)

        wlcalib_aux = np.asarray(wlcalib)
        final, wcsdata = self.resample_rss_flux(rss, wlcalib_aux, indices)

        hdu_f = fits.PrimaryHDU(final)
        hdu_f.writeto('resample_rss.fits', clobber=True)

        fibras.sort()

        suma = np.sum(final[fibras.astype(int),lambda1:lambda2],axis=1)
        sky = np.min(suma)
        sumaparcial = suma - sky

        neigh_info = neigh_info[np.argsort(neigh_info[:, 0])]

        centroid_x = np.multiply(sumaparcial,neigh_info[:,2])
        centroid_x = np.sum(centroid_x, axis=0)

        centroid_y = np.multiply(sumaparcial,neigh_info[:,3])
        centroid_y = np.sum(centroid_y, axis=0)

        sumatotal = np.sum(sumaparcial, axis=0)
        self.logger.info( "total sum: %s", sumatotal)

        second_order = []
        aux = np.sum(np.multiply(suma,(neigh_info[:,2] - np.mean(neigh_info[:,2]))**2),axis=0)
        second_order.append(np.divide(aux ,np.sum(suma, axis=0)))
        self.logger.info("Second order momentum X: %s", second_order[0])

        aux = np.sum(np.multiply(suma,(neigh_info[:,3] - np.mean(neigh_info[:,3]))**2),axis=0)
        second_order.append(np.divide(aux ,np.sum(suma, axis=0)))
        self.logger.info("Second order momentum Y: %s", second_order[1])

        aux = np.multiply(neigh_info[:,3] - np.mean(neigh_info[:,3]),neigh_info[:,2] - np.mean(neigh_info[:,2]))
        aux = np.sum(np.multiply(aux,suma))
        cov = np.divide(aux ,np.sum(suma, axis=0))
        self.logger.info("Cov X,Y: %s", cov)

        centroid_x = np.divide(centroid_x, sumatotal)
        self.logger.info( "centroid_x: %s", centroid_x)

        centroid_y = np.divide(centroid_y, sumatotal)
        self.logger.info("centroid_y: %s", centroid_y)

        centroid = [centroid_x, centroid_y]

        peak = np.sum(final[grid.get_fiber(centroid),lambda1:lambda2],axis=0)

        return centroid, sky, peak, second_order, cov

    def generate_solution(self, points, centroid, sky, fiber, peaks, second_order, cova):
        result = []
        for cont, value in enumerate(points):
            lista = (value[0], value[1], centroid[cont][0],centroid[cont][1], sky[cont], fiber[cont], peaks[cont], second_order[cont][0], second_order[cont][1], cova[cont])
            result.append(lista)
        return np.array(result, dtype=[('x_point','float'),('y_point','float'),('x_centroid','float'),('y_centroid','float'), ('sky','float'),('fiber','int'),('peak','float'),('x_second_order','float'), ('y_second_order','float'), ('covariance','float') ])

    def generateJSON(self, points, centroid, sky, fiber, peaks, second_order, cova):
        '''
        '''

        self.logger.info('start JSON generation')

        result = []
        for cont, value in enumerate(points):
            obj = {
                'points': value,
                'centroid': centroid[cont],
                'sky':sky[cont],
                'fiber': fiber[cont],
                'peak': peaks[cont],
                'second_order': second_order[cont],
                'covariance': cova[cont]
            }
            result.append(obj)

        self.logger.info('end JSON generation')

        return result

    def compute_dar(self, img):
        import numpy.polynomial.polynomial as pol
        import astropy.wcs

        fiberconf = self.datamodel.get_fiberconf(img)
        wlcalib = astropy.wcs.WCS(img[0].header)

        rssdata = img[0].data
        cut1 = 500
        cut2 = 3500
        colids = []
        x = []
        y = []
        for fiber in fiberconf.fibers.values():
            colids.append(fiber.fibid - 1)
            x.append(fiber.x)
            y.append(fiber.y)

        cols = []
        xdar = []
        ydar = []
        delt = 50

        point = [2.0, 2.0]
        # Start in center of range
        ccenter = (cut2 + cut1) // 2
        # Left
        for c in range(ccenter, cut1, -delt):
            c1 = c - delt // 2
            c2 = c + delt // 2

            z = rssdata[colids, c1:c2].mean(axis=1)
            centroid = self.centroid(rssdata, fiberconf, c1, c2, point)
            cols.append(c)
            xdar.append(centroid[0])
            ydar.append(centroid[1])
            point = centroid

        cols.reverse()
        xdar.reverse()
        ydar.reverse()

        point = [2.0, 2.0]
        # Star over
        # Right
        for c in range(ccenter, cut2, delt):
            c1 = c - delt // 2
            c2 = c + delt // 2
            print(c1, c2)
            z = rssdata[colids, c1:c2].mean(axis=1)
            centroid = self.centroid(rssdata, fiberconf, c1, c2, point)
            cols.append(c)
            xdar.append(centroid[0])
            ydar.append(centroid[1])
            point = centroid

        rr = [[col, 0] for col in cols]
        world = wlcalib.wcs_pix2world(rr, 0)

        if False:
            import matplotlib.pyplot as plt
            import megaradrp.visualization as vis
            import megaradrp.simulation.refraction as r
            from astropy import units as u

            plt.subplots_adjust(hspace=0.5)
            plt.subplot(111)
            ax = plt.gca()
            plt.xlim([-8, 8])
            plt.ylim([-8, 8])
            col = vis.hexplot(ax, x, y, z, cmap=plt.cm.YlOrRd_r)
            plt.title("Fiber map, %s %s" % (c1, c2))
            cb = plt.colorbar(col)
            cb.set_label('counts')
            plt.show()

            zenith_distance = 60 * u.deg
            press = 79993.2 * u.Pa
            rel = 0.013333333
            temp = 11.5 * u.deg_C

            ll = r.differential_p(
                    zenith_distance,
                    wl=world[:,0] * u.AA,
                    wl_reference=4025 * u.AA,
                    temperature=temp,
                    pressure=press,
                    relative_humidity=rel,
            )
            plt.plot(world[:,0], xdar, '*-')
            plt.plot(world[:,0], ydar, '*-')
            plt.plot(world[:, 0], 2.0 * u.arcsec + ll.to(u.arcsec), '-')
            plt.show()

        # fit something

        print('DAR, x:', pol.polyfit(world[:, 0], xdar, deg=3))
        print('DAR: y:', pol.polyfit(world[:, 0], ydar, deg=3))

    def centroid(self, rssdata, fiberconf, c1, c2, point):
        from scipy.spatial import KDTree

        self.logger.debug("LCB configuration is %s", fiberconf.conf_id)

        fibers = fiberconf.conected_fibers(valid_only=True)
        grid_coords = []
        for fiber in fibers:
            grid_coords.append((fiber.x, fiber.y))
        # setup kdtree for searching
        kdtree = KDTree(grid_coords)

        # Other posibility is
        # query using radius instead
        # radius = 1.2
        # kdtree.query_ball_point(points, k=7, r=radius)

        npoints = 19
        # 1 + 6  for first ring
        # 1 + 6  + 12  for second ring
        # 1 + 6  + 12  + 18 for third ring
        points = [point]
        dis_p, idx_p = kdtree.query(points, k=npoints)

        self.logger.info('Using %d nearest fibers', npoints)
        for diss, idxs, point in zip(dis_p, idx_p, points):
            # For each point
            self.logger.info('For point %s', point)
            colids = []
            coords = []
            for dis, idx in zip(diss, idxs):
                fiber = fibers[idx]
                colids.append(fiber.fibid - 1)
                coords.append((fiber.x, fiber.y))

            coords = np.asarray(coords)
            flux_per_cell = rssdata[colids, c1:c2].mean(axis=1)
            flux_per_cell_total = flux_per_cell.sum()
            flux_per_cell_norm = flux_per_cell / flux_per_cell_total
            # centroid
            scf = coords.T * flux_per_cell_norm
            centroid = scf.sum(axis=1)
            self.logger.info('centroid: %s', centroid)
            # central coords
            c_coords = coords - centroid
            scf0 = scf - centroid[:, np.newaxis] * flux_per_cell_norm
            mc2 = np.dot(scf0, c_coords)
            self.logger.info('2nd order moments, x2=%f, y2=%f, xy=%f', mc2[0,0], mc2[1,1], mc2[0,1])
            return centroid


def copy_img(img):
    return fits.HDUList([hdu.copy() for hdu in img])