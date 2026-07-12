from glob import glob
from setuptools import find_packages, setup


package_name = 'car_vision'


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
    description='Vision detection and tracking nodes for the iCar ROS2 smart car.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'color_detector = car_vision.color_detector:main',
            'color_tracker = car_vision.color_tracker:main',
            'yolo_detector = car_vision.yolo_detector:main',
            'person_detector = car_vision.person_detector:main',
        ],
    },
)
