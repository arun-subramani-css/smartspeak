import os
import pytest

# Ensure MONGODB_URI is always present during test executions
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/smartspeak_test"
