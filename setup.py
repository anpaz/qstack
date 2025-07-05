from setuptools import setup, find_packages

tools = ["ruff", "black"]

setup(
    name="qstack",
    version="0.1.0",
    author="Andres Paz",
    author_email="anpaz@cs.washington.edu",
    description="qstack: a framework for quantum compilers.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/anpaz/qstack",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "numpy",
        "matplotlib",
        "qsharp",
    ],
    extras_require={
        "qiskit": ["qiskit", "qiskit-aer"],
    },
)
