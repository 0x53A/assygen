# AssyGen - Assembly Drawing Generator

AssyGen is a tool for generating PDFs for PCB assembly.

## Installation

This project uses `uv` for dependency management. 

## Usage

```bash
uv run assygen.py [--verbose] <path>

# Example:
uv run assygen ./kicad-test/freewatch
```

You'll need to pass the base file path, that is, without extension. The tool will auto-detect related files.

### Supported Files

**Position Files (Required):**
- `<base_name>.CSV` or `<base_name>.csv` - Combined position file (old format)
- `<base_name>-all-pos.csv` - Combined position file (new KiCad format)  
- `<base_name>_pos.csv` - Alternative combined format
- `<base_name>-top.pos` + `<base_name>-bottom.pos` - Separate position files

*KiCad Export:* `File → Fabrication Outputs → Footprint Position (.pos) file`

**Gerber Files (Required):**
- **Old naming convention:**
  - `<base_name>.GTL` - Top copper layer
  - `<base_name>.GTO` - Top silkscreen/overlay
  - `<base_name>.GBL` - Bottom copper layer  
  - `<base_name>.GBO` - Bottom silkscreen/overlay
- **New naming convention:**
  - `<base_name>-F_Cu.gbr` - Front (top) copper layer
  - `<base_name>-F_Silkscreen.gbr` - Front (top) silkscreen
  - `<base_name>-B_Cu.gbr` - Back (bottom) copper layer
  - `<base_name>-B_Silkscreen.gbr` - Back (bottom) silkscreen

*KiCad Export:* `File → Fabrication Outputs → Gerber Files (.gbr)`

**Drill Files (Optional):**
- `<base_name>-PTH.drl` - Plated through holes
- `<base_name>-NPTH.drl` - Non-plated through holes  
- `<base_name>.drl` - Combined drill file (legacy format)

*KiCad Export:* `File → Fabrication Outputs → Drill Files (.drl)`

**Report Files (Optional):**
- `<base_name>.rpt` - KiCad footprint report for accurate component dimensions

*KiCad Export:* `File → Fabrication Outputs → Component Report`
