from setuptools import setup, find_packages

setup(
    name="dat-dashboard",
    version="0.1.0",
    description="Digital Asset Treasury Dashboard",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.31.0",
        "anthropic>=0.18.0",
        "pyyaml>=6.0.1",
        "beautifulsoup4>=4.12.3",
        "python-dotenv>=1.0.1",
        "lxml>=5.1.0",
    ],
    entry_points={
        "console_scripts": [
            "dat-dashboard=src.main:main",
        ],
    },
)
