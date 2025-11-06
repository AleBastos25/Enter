import traceback
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.batch_process import process_folder

try:
    process_folder('data/samples', 'test_output_v3.json', debug=True)
except Exception as e:
    traceback.print_exc()

