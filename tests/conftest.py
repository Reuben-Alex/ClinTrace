"""Pytest configuration for ClinTrace."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: live API tests (requires GOOGLE_API_KEY and network)",
    )
