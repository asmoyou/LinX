"""
Setup configuration for LinX (灵枢)
"""

from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="linx-platform",
    version="1.0.0",
    author="LinX Team",
    author_email="team@linx.platform",
    description="LinX (灵枢) - Intelligent Collaboration Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/digital-workforce-platform",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Framework :: FastAPI",
    ],
    python_requires=">=3.11",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "langchain>=0.1.4",
        "psycopg2-binary>=2.9.9",
        "sqlalchemy>=2.0.25",
        "pymilvus>=2.3.5",
        "minio>=7.2.3",
        "redis>=5.0.1",
        "python-jose[cryptography]>=3.3.0",
        "passlib[bcrypt]>=1.7.4",
        "pydantic>=2.5.3",
        "pydantic-settings>=2.1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.4",
            "pytest-asyncio>=0.23.3",
            "pytest-cov>=4.1.0",
            "black>=24.1.1",
            "flake8>=7.0.0",
            "mypy>=1.8.0",
            "isort>=5.13.2",
        ],
        "docs": [
            "sphinx>=7.2.6",
            "sphinx-rtd-theme>=2.0.0",
        ],
        "llm": [
            "ollama>=0.1.6",
            "openai>=1.10.0",
            "anthropic>=0.8.1",
        ],
        "document": [
            "PyPDF2>=3.0.1",
            "pdfplumber>=0.10.3",
            "python-docx>=1.1.0",
            "python-pptx>=1.0.2",
            "pytesseract>=0.3.10",
            "openai-whisper>=20231117",
        ],
    },
    entry_points={
        "console_scripts": [
            "workforce-api=api_gateway.main:main",
            "workforce-worker=task_manager.worker:main",
        ],
    },
)
