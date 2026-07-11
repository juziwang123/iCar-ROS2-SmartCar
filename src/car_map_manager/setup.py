from setuptools import find_packages, setup


package_name = 'car_map_manager'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        (f'share/{package_name}', ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='iCar Team',
    maintainer_email='team@example.com',
    description='Managed map metadata and validation for iCar.',
    license='MIT',
    tests_require=['pytest'],
)
