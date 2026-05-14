"""
Setup configuration for MeterHub Python Client SDK
"""

from setuptools import setup, find_packages

with open("meterhub_client/README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="meterhub-client",
    version="1.0.0",
    author="MeterHub Team",
    author_email="dev@meterhub.io",
    description="Python client SDK for MeterHub edge gateway devices",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yugeshmluv/pi-zero-meter-gateway",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=[
        "aiohttp>=3.8.0",
        "certifi>=2022.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.18.0",
            "pytest-cov>=3.0",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=0.950",
        ],
    },
    project_urls={
        "Bug Tracker": "https://github.com/yugeshmluv/pi-zero-meter-gateway/issues",
        "Documentation": "https://docs.meterhub.io/sdk/python",
        "Source Code": "https://github.com/yugeshmluv/pi-zero-meter-gateway",
    },
)
