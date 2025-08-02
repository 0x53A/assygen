from assygen import main as assygen_main
import sys
import os

def print_help():
    """Print help information"""
    print("""
Usage: uv run main.py <base_name> [directory] [--verbose]

Arguments:
  base_name     Base name of your project files (without extensions)
  directory     Optional: Directory containing the files (default: current)
  --verbose     Optional: Enable detailed Gerber parsing output

Examples:
  uv run main.py freewatch                          # Files in current directory  
  uv run main.py my_project /path/to/exports        # Files in specific directory
  uv run main.py freewatch . --verbose              # Enable verbose Gerber analysis

File Requirements:
  Position files (one of):
    - <base_name>.CSV                               # Combined format
    - <base_name>-top.pos + <base_name>-bottom.pos  # Separate format
  
  Gerber files (old or new naming):
    - Old: <base_name>.GTL/.GTO/.GBL/.GBO
    - New: <base_name>-F_Cu.gbr/-F_Silkscreen.gbr/-B_Cu.gbr/-B_Silkscreen.gbr

Output:
  <base_name>_assy.pdf - Multi-page assembly drawing with component tables

Features:
  • Automatic landscape/portrait orientation based on PCB dimensions
  • Professional bordered component tables with color coding
  • Smooth Gerber rendering with arc interpolation
  • Support for both old and new KiCad file naming conventions
""")

def main():
    print("AssyGen - Assembly Drawing Generator for PCBs")
    print("=" * 50)
    
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print_help()
        sys.exit(0)
    
    if sys.argv[1] in ['--version', '-v']:
        print("AssyGen v2.0 - Modern Python 3 Assembly Drawing Generator")
        print("Features: Auto-orientation, smooth Gerber rendering, professional tables")
        sys.exit(0)
    
    if len(sys.argv) < 2:
        print("Usage: assygen <base_name> [directory] [--verbose]")
        print("Examples:")
        print("  assygen freewatch                    # Files in current directory")
        print("  assygen freewatch /path/to/files     # Files in specified directory")
        print("  assygen /full/path/to/basename       # Full path to base name")
        print("  assygen freewatch . --verbose        # Enable verbose Gerber parsing")
        print("\nGenerates assembly drawings with Gerber PCB backgrounds")
        sys.exit(1)
    
    # Check for verbose flag
    verbose = '--verbose' in sys.argv
    
    # Filter out flags to get positional arguments
    args = [arg for arg in sys.argv[1:] if not arg.startswith('-')]
    
    if len(args) < 1:
        print("Error: Missing required argument <base_name>")
        sys.exit(1)
    
    # Parse arguments (excluding flags)
    if len(args) >= 2:
        # Directory specified
        base_name = args[0]
        directory = args[1]
        full_base_path = os.path.join(directory, base_name)
    elif os.path.dirname(args[0]):
        # Full path provided
        full_base_path = args[0]
        directory = os.path.dirname(full_base_path)
        base_name = os.path.basename(full_base_path)
    else:
        # Just base name, use current directory
        base_name = args[0]
        directory = "."
        full_base_path = base_name
    
    print(f"Looking for files with base name: {base_name}")
    print(f"In directory: {os.path.abspath(directory)}")
    
    # Check for pick-and-place CSV file (try multiple naming conventions)
    csv_candidates = [
        full_base_path + ".CSV",           # Old convention (uppercase)
        full_base_path + ".csv",           # Old convention (lowercase)
        full_base_path + "-all-pos.csv",   # New KiCad convention (combined)
        full_base_path + "_pos.csv",       # Alternative convention
    ]
    
    # Also check for separate top/bottom pos files
    pos_top = full_base_path + "-top.pos"
    pos_bottom = full_base_path + "-bottom.pos"
    
    csv_file = None
    use_separate_pos_files = False
    
    # First try to find a combined CSV file
    for candidate in csv_candidates:
        if os.path.exists(candidate):
            csv_file = candidate
            break
    
    # If no combined CSV, check for separate .pos files
    if not csv_file:
        if os.path.exists(pos_top) or os.path.exists(pos_bottom):
            use_separate_pos_files = True
            print(f"Found separate position files:")
            if os.path.exists(pos_top):
                print(f"  ✓ {os.path.basename(pos_top)}")
            if os.path.exists(pos_bottom):
                print(f"  ✓ {os.path.basename(pos_bottom)}")
        else:
            print("Error: No pick-and-place files found!")
            print("Tried looking for:")
            for candidate in csv_candidates:
                print(f"  - {os.path.basename(candidate)}")
            print(f"  - {os.path.basename(pos_top)}")
            print(f"  - {os.path.basename(pos_bottom)}")
            print("\nYou need to generate position files from KiCad:")
            print("  File → Fabrication Outputs → Footprint Position (.pos) file")
            sys.exit(1)
    else:
        print(f"Found pick-and-place file: {os.path.basename(csv_file)}")
    
    # Check for Gerber files (both old and new naming conventions)
    gerber_candidates = [
        # Old convention
        (full_base_path + ".GTL", "Top copper (old)"),
        (full_base_path + ".GTO", "Top silkscreen (old)"),
        (full_base_path + ".GBL", "Bottom copper (old)"), 
        (full_base_path + ".GBO", "Bottom silkscreen (old)"),
        # New convention
        (full_base_path + "-F_Cu.gbr", "Top copper (new)"),
        (full_base_path + "-F_Silkscreen.gbr", "Top silkscreen (new)"),
        (full_base_path + "-B_Cu.gbr", "Bottom copper (new)"),
        (full_base_path + "-B_Silkscreen.gbr", "Bottom silkscreen (new)"),
    ]
    
    found_gerber = []
    missing_gerber = []
    
    for file_path, description in gerber_candidates:
        if os.path.exists(file_path):
            found_gerber.append((file_path, description))
        else:
            missing_gerber.append((file_path, description))
    
    if found_gerber:
        print("Found Gerber files:")
        for file_path, description in found_gerber:
            print(f"  ✓ {os.path.basename(file_path)} ({description})")
    
    if missing_gerber:
        print("Missing Gerber files:")
        for file_path, description in missing_gerber:
            print(f"  - {os.path.basename(file_path)} ({description})")
    
    if not found_gerber:
        print("\nError: No Gerber files found!")
        print("Make sure you have exported Gerber files from KiCad:")
        print("  File → Fabrication Outputs → Gerbers (.gbr)")
        sys.exit(1)
    
    # Change to the target directory so assygen can find the files
    original_dir = os.getcwd()
    try:
        os.chdir(directory)
        print(f"Changed to directory: {os.getcwd()}")
        print("Generating assembly drawings with Gerber backgrounds...")
        
        # Set the base name for assygen (without directory path)
        sys.argv[1] = base_name
        
        # Pass information about file format to assygen
        if use_separate_pos_files:
            sys.argv.append("--separate-pos")
        
        # Pass verbose flag to assygen
        if verbose:
            sys.argv.append("--verbose")
            
        assygen_main()
        
    finally:
        os.chdir(original_dir)

if __name__ == "__main__":
    main()
