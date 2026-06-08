import os
import sys
import tempfile

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.tools.shell import ShellSession
from configs.shell import ShellConfig

# Create a temporary directory for testing
with tempfile.TemporaryDirectory() as temp_dir:
    # Create runs directory
    runs_dir = os.path.join(temp_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    
    # Create a simple ShellConfig
    cfg = ShellConfig()
    
    print("Testing ShellSession on Windows...")
    print(f"Using shell: {'cmd.exe' if os.name == 'nt' else 'bash'}")
    
    try:
        # Create a ShellSession
        session = ShellSession(temp_dir, cfg)
        print("ShellSession created successfully!")
        
        # Test running a simple command
        import asyncio
        
        async def test_command():
            result = await session.run("echo Hello, World!")
            print(f"Command output: {result.strip()}")
            return result
        
        output = asyncio.run(test_command())
        print("Command executed successfully!")
        
        # Test another command
        async def test_dir():
            result = await session.run("dir" if os.name == "nt" else "ls -la")
            print(f"Directory listing:\n{result}")
            return result
        
        output = asyncio.run(test_dir())
        print("Directory listing executed successfully!")
        
        print("All tests passed! The shell fix is working correctly.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if 'session' in locals():
            # Close the process
            session.proc.terminate()
            session.proc.wait()
