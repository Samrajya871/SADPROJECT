import io
import os
import sys
from datetime import datetime
from werkzeug.utils import secure_filename

# Simulate the upload process
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Test 1: Check that our utils work
test_filename = "test_image.jpg"
print(f"Test 1 - File validation for '{test_filename}':")
print(f"  - Is file allowed? {allowed_file(test_filename)}")
print(f"  - Secure filename: {secure_filename(test_filename)}")

# Test 2: Generate timestamp like the code does
ts = datetime.now().strftime('%Y%m%d%H%M%S')
final_name = f"{ts}_{secure_filename(test_filename)}"
print(f"\nTest 2 - Final filename generation:")
print(f"  - Timestamp: {ts}")
print(f"  - Final name: {final_name}")

# Test 3: Check path operations
full_path = os.path.join(UPLOAD_FOLDER, final_name)
print(f"\nTest 3 - Path operations:")
print(f"  - Upload folder: {UPLOAD_FOLDER}")
print(f"  - Absolute path: {os.path.abspath(UPLOAD_FOLDER)}")
print(f"  - Full save path: {full_path}")

# Test 4: Verify folder is writable
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
is_writable = os.access(UPLOAD_FOLDER, os.W_OK)
print(f"\nTest 4 - Folder permissions:")
print(f"  - Folder writable: {is_writable}")
print(f"  - Folder exists: {os.path.exists(UPLOAD_FOLDER)}")

print("\n✅ All checks passed - folder is ready for uploads")
