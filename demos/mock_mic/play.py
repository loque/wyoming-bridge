"""Mock Mic Play Client"""

import argparse
import asyncio
import sys
from pathlib import Path

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Filepath relative to the wavs directory")
    parser.add_argument("--command-port", type=int, default=10102, help="Port for the command server")
    parser.add_argument("--command-host", default="localhost", help="Host for the command server")
    return parser.parse_args()

async def main() -> None:
    """Main function to send a play command."""
    args = parse_arguments()

    # Validate filepath
    script_dir = Path(__file__).parent
    wavs_dir = script_dir / "wavs"
    filepath = wavs_dir / args.filename

    if not filepath.exists():
        print(f"Audio file not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    
    if not filepath.suffix.lower() == ".wav":
        print(f"File is not a WAV file: {filepath}", file=sys.stderr)
        sys.exit(1)

    try:
        reader, writer = await asyncio.open_connection(args.command_host, args.command_port)
        
        print(f"Sending command to play: {args.filename}")
        writer.write(str(filepath).encode())
        await writer.drain()

        response = await reader.read(100)
        print(f"Received response: {response.decode()}")

        writer.close()
        await writer.wait_closed()
    except ConnectionRefusedError:
        print(f"Connection refused. Is the mock mic server running on {args.command_host}:{args.command_port}?", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())