from importlib.metadata import entry_points
from setuptools import setup, find_packages

setup(
    name='pyLOSTwheel',
    version='0.0.1',
    author='Mike Zheng',
    author_email='xzheng902@gmail.com',
    description='Python GUI for data acquisition of LOSTwheel',
    packages=find_packages(),
    install_requires=[
        "pyserial",
        "PySide6",
        "matplotlib",
    ],
    entry_points={
        'console_scripts': ['pyLOSTwheel=pyLOSTwheel.app:main'],
    },
)