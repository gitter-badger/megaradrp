
from setuptools import find_packages
from setuptools import setup


setup(
    name='megaradrp',
    version='0.6.dev1',
    author='Sergio Pascual',
    author_email='sergiopr@fis.ucm.es',
    url='https://github.com/guaix-ucm/megaradrp',
    license='GPLv3',
    description='MEGARA Data Reduction Pipeline',
    packages=find_packages(),
    package_data={
        'megaradrp': [
            'drp.yaml',
        ],
        'megaradrp.instrument.configs': [
            'primary.txt',
            'lcb_default_header.txt',
            'mos_default_header.txt',
            'component-06fc5d6d-d20b-4eba-b3fa-57696f0a1103.json',
            'component-2e02e135-2325-47c9-9975-466b445b0b8b.json',
            'component-715c7ced-f989-42a6-bb74-a5b5cda0495c.json',
            'component-86a6e968-8d3d-456f-89f8-09ff0c7f7c57.json',
            'component-97d48545-3258-473e-9311-00e390999d52.json',
            'instrument-4fd05b24-2ed9-457b-b563-a3c618bb1d4c.json',
            'instrument-66f2283e-3049-4d4b-8ef1-14d62fcb611d.json',
            'instrument-9a86b2b2-3f7d-48ec-8f4f-3780ec967c90.json'
        ],
    },
    install_requires=[
        'numpy',
        'astropy >= 1.0',
        'scipy',
        'numina >= 0.14',
        'scikit-image',
    ],
    zip_safe=False,
    entry_points={
        'numina.pipeline.1': [
        '   MEGARA = megaradrp.loader:load_drp',
            ],
        },
        classifiers=[
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3.4",
            "Programming Language :: Python :: 3.5",
            'Development Status :: 3 - Alpha',
            "Environment :: Other Environment",
            "Intended Audience :: Science/Research",
            "License :: OSI Approved :: GNU General Public License (GPL)",
            "Operating System :: OS Independent",
            "Topic :: Scientific/Engineering :: Astronomy",
        ],
    long_description=open('README.rst').read()
)
