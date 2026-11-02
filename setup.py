from setuptools import setup, find_packages

setup(
    name="billflow",
    version="6.0.0",
    packages=find_packages(),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "matplotlib>=3.7.0",
        "pillow>=9.5.0",
    ],
    extras_require={
        "desktop": ["PySide6>=6.5.0"],
    },
    entry_points={
        "console_scripts": [
            "billflow=run_modern:main",
            "billflow-classic=run:main",
        ],
    },
)
