from setuptools import find_packages, setup


package_name = 'car_bringup'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
        (f'share/{package_name}/launch', [
            'launch/bringup.launch.py',
            'launch/node_manager.launch.py',
            'launch/runtime_profile.launch.py',
            'launch/vendor_x3_base_no_joy.launch.py',
        ]),
        (f'share/{package_name}/config', ['config/params.yaml', 'config/lidar.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Bringup launch files for the iCar ROS2 smart car.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'icar = car_bringup.icar_cli:main',
            'odom_tf_keepalive = car_bringup.odom_tf_keepalive:main',
        ],
    },
)
