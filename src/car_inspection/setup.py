from glob import glob
from setuptools import find_packages, setup


package_name = 'car_inspection'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
        (f'share/{package_name}/launch', glob('launch/*.launch.py')),
        (f'share/{package_name}/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Checkpoint verification and evidence storage for iCar.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'checkpoint_verifier = car_inspection.checkpoint_verifier:main',
            'inspection_executor = car_inspection.inspection_executor:main',
            'qr_detector = car_inspection.qr_detector:main',
        ],
    },
)
