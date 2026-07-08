import os
from setuptools import setup

package_name = 'car_vision'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            ['launch/vision.launch.py']),
        (os.path.join('share', package_name, 'config'),
            ['config/vision_params.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='iCar ROS2 vision package for object detection and tracking',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'color_detector = car_vision.color_detector:main',
            'color_tracker = car_vision.color_tracker:main',
            'yolo_detector = car_vision.yolo_detector:main',
            'line_follower = car_vision.line_follower:main',
            'defect_detector = car_vision.defect_detector:main',
        ],
    },
)
