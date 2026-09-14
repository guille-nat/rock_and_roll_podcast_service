import os

# Settings are read when app.main is imported, so the environment must be
# in place before any test module imports the application.
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://podcasts:podcasts@localhost:5432/podcasts_test"
)
