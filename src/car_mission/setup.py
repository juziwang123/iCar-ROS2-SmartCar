from glob import glob
from setuptools import find_packages, setup


package_name = 'car_mission'


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
    description='Mission execution for the iCar patrol system.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'mission_manager = car_mission.mission_manager:main',
            'health_monitor = car_mission.health_monitor:main',
        ],
    },
)
