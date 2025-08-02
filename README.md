# AssyGen - Assembly Drawing Generator

AssyGen is a tool for generating professional assembly drawings for PCBs from pick-and-place data and Gerber files.

## Features

- **Complete PCB visualization**: Renders Gerber files as realistic PCB backgrounds with smooth curves and arcs
- **Automatic orientation**: Intelligently chooses landscape/portrait based on PCB dimensions for optimal space usage
- **Multi-layer support**: Processes both top (F.Cu) and bottom (B.Cu) layers with proper scaling
- **Professional tables**: Clean bordered component tables with color coding and proper layout
- **Flexible file formats**: Supports both combined CSV and separate .pos files (newer KiCad format)
- **Dual naming conventions**: Works with both old (.GTL/.GTO) and new (-F_Cu.gbr/-F_Silkscreen.gbr) Gerber naming
- **Color-coded component placement**: Groups components by value with distinct colors
- **Professional PDF output**: Multi-page documents with assembly guides and component tables
- **KiCad compatibility**: Works directly with KiCad pick-and-place CSV/pos files
- **Modern Python 3**: Built with contemporary libraries and practices

## Installation

This project uses `uv` for dependency management. Make sure you have `uv` installed.

```bash
# Clone or navigate to the project directory
cd assygen

# Install dependencies
uv sync
```

## Usage

```bash
# Generate assembly drawing from pick-and-place data and Gerber files
uv run main.py <base_name> [directory] [--verbose]

# Examples:
uv run main.py freewatch                           # Files in current directory
uv run main.py project_name /path/to/gerber/files  # Files in different directory
uv run main.py freewatch . --verbose               # Enable verbose Gerber parsing
```

**Command line options:**
- `<base_name>`: Base name of your PCB files (required)
- `[directory]`: Directory containing the files (optional, defaults to current directory)  
- `--verbose`: Enable detailed Gerber parsing output, shows any unrecognized/skipped commands
- `--help`: Show help message with usage examples
- `--version`: Show version information

The tool automatically:
1. Detects file format (combined CSV vs separate .pos files)
2. Finds Gerber files using either naming convention
3. Analyzes PCB dimensions for optimal orientation
4. Generates `<base_name>_assy.pdf` with complete assembly drawings

### Supported File Formats

**Position Files:**
- `<base_name>.CSV` (combined, older KiCad format)
- `<base_name>-top.pos` + `<base_name>-bottom.pos` (separate, newer KiCad format)

**Gerber Files:**
- Old: `<base_name>.GTL/.GTO/.GBL/.GBO`
- New: `<base_name>-F_Cu.gbr/-F_Silkscreen.gbr/-B_Cu.gbr/-B_Silkscreen.gbr`

### Verbose Mode

Use the `--verbose` flag to enable detailed Gerber parsing analysis:

```bash
uv run main.py freewatch . --verbose
```

In verbose mode, the tool will:
- Display all unrecognized Gerber commands (helps identify parser gaps)
- Show skipped commands that are acknowledged but not implemented
- Confirm when all commands in a file are fully recognized
- Help diagnose issues with complex Gerber files

This is useful for:
- Debugging Gerber parsing issues
- Understanding parser completeness 
- Validating that your Gerber files are fully supported

## Input Files

### Required Files
- **Pick-and-Place CSV**: `<base_name>.CSV` 
- **Gerber Files**:
  - `<base_name>.GTL` - Top copper layer
  - `<base_name>.GTO` - Top silkscreen overlay  
  - `<base_name>.GBL` - Bottom copper layer
  - `<base_name>.GBO` - Bottom silkscreen overlay

### Pick-and-Place CSV Format
The tool expects KiCad-style pick-and-place CSV files with these columns:
- `Ref`: Component reference (e.g., C1, R2, U3)
- `Val`: Component value/description  
- `PosX`: X position in mm
- `PosY`: Y position in mm
- `Side`: PCB side (`F.Cu` for top, `B.Cu` for bottom)

Example:
```
Ref    Val                  Package         PosX       PosY        Rot     Side
C14    100nF               Capacitor       106.3036  -107.7576     270.0    B.Cu
R21    10K                 Resistor        100.7827   -95.2834      90.0    B.Cu
```

## Output

The tool generates a comprehensive multi-page PDF with:
- **Realistic PCB backgrounds**: Rendered from actual Gerber files
- **Color-coded component rectangles**: Show exact placement positions
- **Component tables**: Detailed legends with part groupings
- **Both layers**: Separate pages for top and bottom assembly
- **Professional scaling**: Automatically fits to page with proper margins

## Architecture

The project structure:
- `main.py`: Entry point and argument handling
- `assygen.py`: Core assembly drawing generation logic
- `modern_gerber.py`: Modern Python 3 Gerber file parser
- `gerber2pdf.py`: Legacy Gerber processor (kept for reference)

## Technical Details

### Modern Gerber Parser
AssyGen includes a custom-built Gerber file parser that:
- Replaces the outdated `plex` dependency with regex-based parsing  
- Handles RS-274X format Gerber files with full arc interpolation support
- Supports circles, rectangles, lines, and smooth curved traces
- Renders G02/G03 circular interpolation as smooth arcs (not segments)
- Calculates proper extents for automatic scaling
- Uses round line caps for professional appearance

### Dependencies
- `reportlab`: Professional PDF generation
- `modern_gerber`: Custom Gerber file processing
- Python 3.13+

## Example Output

For the included test case (`freewatch`):
- Processes 47 components across top and bottom layers
- Generates 9 pages total (5 for top, 4 for bottom)
- Each page shows 6 component groups with color coding
- Full PCB background with copper traces and silkscreen visible
