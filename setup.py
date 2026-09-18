# -*- coding: utf-8 -*-
"""Setup file for the inventree-mbom plugin.

Generated for InvenTree >= 1.3.1
"""

import importlib.util
import os
import setuptools

# Read the plugin version from the source code
module_path = os.path.join(
    os.path.dirname(__file__), "inventree_mbom", "__init__.py"
)
spec = importlib.util.spec_from_file_location("inventree_mbom", module_path)
inventree_mbom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventree_mbom)

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setuptools.setup(
    name="inventree-mbom",
    version=inventree_mbom.PLUGIN_VERSION,
    author="Tim",
    author_email="",
    description="Manufacturing BOM & Routings plugin for InvenTree",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/inventree-mbom",
    license="MIT",
    packages=setuptools.find_packages(exclude=["tests*"]),
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=[
        "inventree>=1.3.1",
    ],
    entry_points={
        "inventree_plugins": [
            "inventree_mbom = inventree_mbom.core:ManufacturingBOMPlugin"
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Django",
    ],
)
