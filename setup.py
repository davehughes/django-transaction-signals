#!/usr/bin/python
import setuptools
setuptools.setup(
    name='django-transaction-signals',
    version='1.0.0',
    packages=setuptools.find_packages(),
    url='https://github.com/davehughes/django-transaction-signals',
    author='David Hughes',
    author_email='d@vidhughes.com',
    description='Adds post_commit and post_rollback signal handlers to Django'
)
