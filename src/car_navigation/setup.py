from setuptools import find_packages, setup


package_name = 'car_navigation'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
        (f'share/{package_name}/launch', [
            'launch/mapping.launch.py',
            'launch/navigation.launch.py',
            'launch/patrol.launch.py',
        ]),
        (f'share/{package_name}/config', [
            'config/waypoints.yaml',
            'config/nav2_params.yaml',
        ]),
        (f'share/{package_name}/maps', [
            'maps/lab_map.yaml',
            'maps/lab_map.pgm',
            'maps/lab_map.png',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Navigation helpers for the iCar ROS2 smart car.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'goal_publisher = car_navigation.goal_publisher:main',
            'waypoint_patrol = car_navigation.waypoint_patrol:main',
        ],
    },
)
