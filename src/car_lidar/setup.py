from setuptools import find_packages, setup


package_name = 'car_lidar'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
        (f'share/{package_name}/launch', ['launch/lidar.launch.py']),
        (f'share/{package_name}/config', ['config/lidar.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Lidar-based safety and perception nodes for the iCar ROS2 smart car.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'avoidance = car_lidar.avoidance:main',
            'tracker = car_lidar.tracker:main',
        ],
    },
)