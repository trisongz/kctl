import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

if sys.version_info.major != 3:
    raise RuntimeError("This package requires Python 3+")

version = '0.0.1'
pkg_name = 'kctl'
gitrepo = 'trisongz/kctl'
root = Path(__file__).parent

requirements = [
    'lazyapi',
    'lazycls',
    'kubernetes',
]

args = {
    'packages': find_packages(include = ['kctl', 'kctl.*']),
    'install_requires': requirements,
    'long_description': root.joinpath('README.md').read_text(encoding='utf-8'),
    'entry_points': {}
}

setup(
    name=pkg_name,
    version=version,
    url=f'https://github.com/{gitrepo}',
    license='MIT Style',
    description='Rancher Kubernetes API compatible with  RKE, RKE2 and maybe others?',
    author='Tri Songz',
    author_email='ts@growthengineai.com',
    long_description_content_type="text/markdown",
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
        'Topic :: Software Development :: Libraries',
    ],
    **args
)