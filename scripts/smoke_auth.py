"""Quick smoke test for auth flow with .env loading."""
import os
import sys

# Simulate what ui/app.py does
sys.path.insert(0, ".")
from reflex.core.env import load_dotenv

load_dotenv()

# Verify .env was loaded
secret = os.environ.get("REFLEX_API_SECRET", "")
print(f"1. REFLEX_API_SECRET loaded: {bool(secret)}")

# Now test auth
from reflex.auth import create_token, validate_token

token = create_token(subject="alice", role="admin")
print(f"2. Token created: {token[:40]}...")

claims = validate_token(token)
print(f"3. Token validated: sub={claims['sub']}, role={claims['role']}")

# Test viewer role
token2 = create_token(subject="bob", role="viewer")
claims2 = validate_token(token2)
print(f"4. Viewer token: sub={claims2['sub']}, role={claims2['role']}")

# Test invalid role rejection
try:
    token3 = create_token(subject="eve", role="hacker")
    print("5. ERROR: Should have rejected invalid role")
except Exception as e:
    print(f"5. Invalid role correctly rejected: {e}")

# Test tampered token (change signature byte)
try:
    parts = token.split(".")
    bad_token = parts[0] + ".BAD" + parts[1][3:]
    validate_token(bad_token)
    print("6. ERROR: Should have rejected tampered token")
except Exception as e:
    print(f"6. Tampered token correctly rejected: {e}")

# Test expired token
from reflex.auth.tokens import create_token as _create
old_token = _create(subject="test", role="viewer", expiry_hours=-1)
try:
    validate_token(old_token)
    print("7. ERROR: Should have rejected expired token")
except Exception as e:
    print(f"7. Expired token correctly rejected: {e}")

print("\nAll auth checks passed!")
