import os
import json
from datetime import datetime
import logging

_LOGGER = logging.getLogger(__name__)


def to_serializable(obj):
    """Recursively convert an object to something JSON serializable."""
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    elif isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [to_serializable(i) for i in obj]
    elif hasattr(obj, '__dict__'):
        return {k: to_serializable(v) for k, v in obj.__dict__.items() if not k.startswith('_')}
    else:
        return str(obj)


def write_json_file(data, filename_prefix="wyoming_info"):
    """Write data as JSON to a uniquely named file in the output directory."""
    try:
        # Get directory of this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        # Create a unique filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = f"{filename_prefix}_{timestamp}.json"
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _LOGGER.debug(f"[INFO] Data written to {file_path}")
    except Exception as e:
        _LOGGER.error(f"[INFO] Failed to write data: {e}")
