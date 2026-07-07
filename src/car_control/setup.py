from setuptools import find_packages, setup


package_name = 'car_control'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
        (f'share/{package_name}/config', ['config/control.yaml']),
        (f'share/{package_name}/launch', ['launch/control.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Control pipeline for iCar ROS2 smart car.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'keyboard_teleop = car_control.keyboard_teleop:main',
            'safety_mux = car_control.safety_mux:main',
            'motion_controller = car_control.motion_controller:main',
        ],
    },
)