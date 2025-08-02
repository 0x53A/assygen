#!/usr/bin/env python3

from modern_gerber import GerberMachine, ResetExtents, gerber_extents
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter, landscape
import csv
import sys
import os

# Global variables for gerber rendering
gerberPageSize = letter
gerberMargin = 0.75 * 25.4 * mm  # 0.75 inch margin
gerberScale = (1.0, 1.0)
gerberOffset = (0.0, 0.0)

def determine_optimal_orientation_with_extents(base_name, verbose=False):
    """Determine optimal PDF orientation based on PCB dimensions"""
    if not gerber_extents or gerber_extents[0] == float('inf'):
        # If no valid extents, default to portrait
        print("No valid PCB extents found - using portrait orientation")
        return letter
    
    # Calculate PCB dimensions
    pcb_width = gerber_extents[2] - gerber_extents[0]  # max_x - min_x
    pcb_height = gerber_extents[3] - gerber_extents[1]  # max_y - min_y
    
    print(f"PCB dimensions: {pcb_width:.2f} x {pcb_height:.2f} units")
    
    # If PCB is wider than tall, use landscape orientation
    if pcb_width > pcb_height:
        print("PCB is wider than tall - using landscape orientation")
        return landscape(letter)
    else:
        print("PCB is taller than wide - using portrait orientation")
        return letter

class PPComponent:
    def __init__(self, xc, yc, w, h, name, desc, ref):
        self.xc = xc
        self.yc = yc
        self.w = w
        self.h = h
        if self.w == 0:
            self.w = 0.8 * mm
        if self.h == 0:
            self.h = 0.8 * mm
        self.name = name
        self.desc = desc
        self.ref = ref

class PickAndPlaceFile:
    def split_parts(self, layer, index, n_comps):
        parts = []
        n = 0
        for i in sorted(self.layers[layer].keys()):
            if n >= index and n < index + n_comps:
                parts.append(self.layers[layer][i])
            n = n + 1
        return parts

    def num_groups(self, layer):
        return len(self.split_parts(layer, 0, 10000))

    def draw(self, layer, index, n_comps, canv):
        parts = self.split_parts(layer, index, n_comps)
        n = 0
        for i in parts:
            canv.setStrokeColor(self.col_map[n])
            canv.setFillColor(self.col_map[n])
            n = n + 1
            for j in i:
                canv.rect(j.xc - j.w/2, j.yc - j.h/2, j.w, j.h, 1, 1)
    
    def gen_table(self, layer, index, n_comps, canv):
        parts = self.split_parts(layer, index, n_comps)

        # Get current page size to position table correctly
        page_width, page_height = gerberPageSize
        
        # Table dimensions and positioning
        table_x = 15 * mm  # Left margin
        table_y = page_height - 35 * mm  # Top position
        
        # Column definitions: x_position, width, header_text
        columns = [
            (0 * mm, 15 * mm, "Color"),
            (15 * mm, 40 * mm, "Lib.Reference"), 
            (55 * mm, 40 * mm, "Comment"),
            (95 * mm, 80 * mm, "Designators")
        ]
        
        table_width = sum(col[1] for col in columns)  # Total width
        row_height = 6 * mm
        header_height = 8 * mm
        
        # Calculate total table height
        num_data_rows = len(parts)
        total_height = header_height + (num_data_rows * row_height)
        
        # Draw heavy outer border
        canv.setLineWidth(2.0)
        canv.setStrokeGray(0)
        canv.rect(table_x, table_y - total_height, table_width, total_height, 0, 0)
        
        # Draw header row background (light gray)
        canv.setFillGray(0.9)
        canv.rect(table_x, table_y - header_height, table_width, header_height, 0, 1)
        
        # Draw heavy border between header and content
        canv.setLineWidth(1.5)
        canv.line(table_x, table_y - header_height, table_x + table_width, table_y - header_height)
        
        # Draw thin vertical column separators
        canv.setLineWidth(0.5)
        x_pos = table_x
        for i, (col_offset, col_width, _) in enumerate(columns[:-1]):  # Skip last column
            x_pos += col_width
            canv.line(x_pos, table_y, x_pos, table_y - total_height)
        
        # Draw thin horizontal row separators
        for i in range(1, num_data_rows):
            y_pos = table_y - header_height - (i * row_height)
            canv.line(table_x, y_pos, table_x + table_width, y_pos)
        
        # Draw header text
        canv.setFont("Helvetica-Bold", 10)
        canv.setFillGray(0)
        text_y = table_y - (header_height * 0.7)  # Center text vertically
        
        for col_offset, col_width, header_text in columns:
            canv.drawString(table_x + col_offset + 2 * mm, text_y, header_text)
        
        # Draw data rows
        canv.setFont("Helvetica", 9)
        n = 0
        for i, group in enumerate(parts):
            row_y = table_y - header_height - (i * row_height)
            text_y = row_y - (row_height * 0.7)  # Center text vertically
            
            # Draw color square in first column
            color_x = table_x + columns[0][0] + 2 * mm
            color_y = row_y - (row_height * 0.8)
            color_size = 4 * mm
            
            canv.setFillColor(self.col_map[n])
            canv.setLineWidth(0.5)
            canv.rect(color_x, color_y, color_size, color_size, 1, 1)
            
            # Reset to black for text
            canv.setFillGray(0)
            n = n + 1
            
            # Build designator string
            dsgn = " ".join(part.name for part in group)
            
            # Draw text in each column (skip color column)
            canv.drawString(table_x + columns[1][0] + 2 * mm, text_y, group[0].ref[0:18])
            canv.drawString(table_x + columns[2][0] + 2 * mm, text_y, group[0].desc[0:18])
            canv.drawString(table_x + columns[3][0] + 2 * mm, text_y, dsgn[0:35])

class PickAndPlaceFileKicad(PickAndPlaceFile):
    def __init__(self, fname):
        print("Loading pick and place file:", fname)
        
        self.col_map = [colors.Color(1,0,0), 
                       colors.Color(1,1,0), 
                       colors.Color(0,1,0), 
                       colors.Color(0,1,1), 
                       colors.Color(1,0,1), 
                       colors.Color(0,0,1)]

        # Parse the CSV file
        with open(fname, 'r') as f:
            rows = []
            for line in f:
                rows.append(line.strip().split())

        # Find column indices
        header = rows[0]
        i_dsg = header.index("Ref")
        i_desc = header.index("Val")
        i_cx = header.index("PosX")
        i_cy = header.index("PosY")
        i_layer = header.index("Side")

        self.layers = {}
        self.layers["Top"] = {}        
        self.layers["Bottom"] = {}
       
        print(f"Column indices - Ref: {i_dsg}, Val: {i_desc}, PosX: {i_cx}, PosY: {i_cy}")
        
        for row in rows[1:]:
            if len(row) > 0:
                cx = float(row[i_cx]) * mm
                cy = float(row[i_cy]) * mm

                w = 1 * mm
                h = 1 * mm
                l = row[i_layer]
                if l == "F.Cu":
                    layer = "Top"
                else:
                    layer = "Bottom"
                    
                ref = row[i_desc]
                if ref not in self.layers[layer]:
                    self.layers[layer][ref] = []
                self.layers[layer][ref].append(PPComponent(cx, cy, w, h, row[i_dsg], row[i_desc], ref))

class PickAndPlaceFileSeparate(PickAndPlaceFile):
    """Handle separate .pos files for top and bottom layers"""
    def __init__(self, base_name):
        import os
        
        self.col_map = [colors.Color(1,0,0), 
                       colors.Color(1,1,0), 
                       colors.Color(0,1,0), 
                       colors.Color(0,1,1), 
                       colors.Color(1,0,1), 
                       colors.Color(0,0,1)]

        self.layers = {}
        self.layers["Top"] = {}        
        self.layers["Bottom"] = {}
        
        # Load top layer file
        top_file = base_name + "-top.pos"
        if os.path.exists(top_file):
            print(f"Loading top layer file: {top_file}")
            self._load_pos_file(top_file, "Top")
        
        # Load bottom layer file  
        bottom_file = base_name + "-bottom.pos"
        if os.path.exists(bottom_file):
            print(f"Loading bottom layer file: {bottom_file}")
            self._load_pos_file(bottom_file, "Bottom")
    
    def _load_pos_file(self, filename, layer):
        """Load a single .pos file"""
        with open(filename, 'r') as f:
            lines = f.readlines()
        
        # Skip header lines (KiCad .pos files start with comments)
        data_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('Ref'):
                data_lines.append(line)
                continue
            # Check if this is the header line
            if line.startswith('Ref') or 'Ref' in line:
                header_line = line
                continue
        
        # If we didn't find data lines, try a different approach
        if not data_lines:
            # Maybe it's space-separated without quotes
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if len(parts) >= 6 and parts[0] != 'Ref':  # Skip header
                        data_lines.append(line)
        
        print(f"Found {len(data_lines)} components in {layer} layer")
        
        for line in data_lines:
            try:
                # Handle both CSV and space-separated formats
                if ',' in line:
                    # CSV format - split by comma and strip quotes
                    parts = [p.strip().strip('"') for p in line.split(',')]
                else:
                    # Space-separated format
                    parts = line.split()
                
                if len(parts) >= 6:
                    ref = parts[0]       # Reference (C1, R2, etc.)
                    val = parts[1]       # Value (100nF, 10K, etc.)  
                    package = parts[2]   # Package/Footprint
                    pos_x = float(parts[3])  # X position
                    pos_y = float(parts[4])  # Y position
                    rotation = float(parts[5])  # Rotation
                    
                    cx = pos_x * mm
                    cy = pos_y * mm
                    w = 1 * mm
                    h = 1 * mm
                    
                    if val not in self.layers[layer]:
                        self.layers[layer][val] = []
                    self.layers[layer][val].append(PPComponent(cx, cy, w, h, ref, val, val))
                    
            except (ValueError, IndexError) as e:
                print(f"Warning: Could not parse line in {filename}: {line}")
                print(f"Error: {e}")
                continue

def find_gerber_files(base_name, layer):
    """Find Gerber files using either old or new KiCad naming conventions"""
    import os
    
    if layer == "Bottom":
        # Try old convention first
        old_copper = base_name + ".GBL"
        old_overlay = base_name + ".GBO"
        # Try new convention
        new_copper = base_name + "-B_Cu.gbr"
        new_overlay = base_name + "-B_Silkscreen.gbr"
    else:
        # Try old convention first
        old_copper = base_name + ".GTL"
        old_overlay = base_name + ".GTO"
        # Try new convention
        new_copper = base_name + "-F_Cu.gbr"
        new_overlay = base_name + "-F_Silkscreen.gbr"
    
    # Check which files exist
    if os.path.exists(old_copper):
        copper_file = old_copper
    elif os.path.exists(new_copper):
        copper_file = new_copper
    else:
        copper_file = None
    
    if os.path.exists(old_overlay):
        overlay_file = old_overlay
    elif os.path.exists(new_overlay):
        overlay_file = new_overlay
    else:
        overlay_file = None
    
    return copper_file, overlay_file

def get_pcb_extents(base_name, verbose=False):
    """Get PCB extents from Gerber files without rendering"""
    # Try both Top and Bottom layers to get overall PCB dimensions
    layers_to_check = ["Top", "Bottom"]
    all_extents = []
    
    for layer in layers_to_check:
        f_copper, f_overlay = find_gerber_files(base_name, layer)
        
        if f_copper or f_overlay:
            # Create a dummy canvas just to calculate extents
            from reportlab.pdfgen import canvas as temp_canvas
            import tempfile
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                temp_name = tmp_file.name
            
            try:
                ctmp = temp_canvas.Canvas(temp_name)
                gm = GerberMachine("", ctmp, verbose=verbose)
                gm.Initialize()
                ResetExtents()
                
                # Process files to get extents
                if f_copper:
                    gm.setColors(colors.Color(0.85, 0.85, 0.85), colors.Color(0, 0, 0))
                    extents = gm.ProcessFile(f_copper)
                    if extents:
                        all_extents.append(extents)
                
                if f_overlay:
                    gm.setColors(colors.Color(0.5, 0.5, 0.5), colors.Color(0, 0, 0))
                    extents = gm.ProcessFile(f_overlay)
                    if extents:
                        all_extents.append(extents)
                
                ctmp.save()
            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_name)
                except:
                    pass
    
    # Combine all extents to get overall PCB bounds
    if all_extents:
        min_x = min(ext[0] for ext in all_extents if ext[0] != float('inf'))
        min_y = min(ext[1] for ext in all_extents if ext[1] != float('inf'))
        max_x = max(ext[2] for ext in all_extents if ext[2] != float('-inf'))
        max_y = max(ext[3] for ext in all_extents if ext[3] != float('-inf'))
        return (min_x, min_y, max_x, max_y)
    
    return None

def determine_optimal_orientation(pcb_extents):
    """Determine optimal page orientation based on PCB dimensions"""
    from reportlab.lib.pagesizes import letter, landscape
    
    if not pcb_extents:
        print("Warning: Could not determine PCB extents, using default orientation")
        return letter
    
    min_x, min_y, max_x, max_y = pcb_extents
    pcb_width = max_x - min_x
    pcb_height = max_y - min_y
    
    print(f"PCB dimensions: {pcb_width/mm:.1f} x {pcb_height/mm:.1f} mm")
    
    # Choose orientation based on PCB aspect ratio
    if pcb_width > pcb_height:
        print("Using landscape orientation for wide PCB")
        return landscape(letter)
    else:
        print("Using portrait orientation for tall/square PCB") 
        return letter

def renderGerber(base_name, layer, canv, verbose=False):
    """Render Gerber files as background layers"""
    global gerber_extents
    
    f_copper, f_overlay = find_gerber_files(base_name, layer)
    
    if not f_copper and not f_overlay:
        print(f"Warning: No Gerber files found for {layer} layer")
        return (0, 0, 100, 100)  # Return dummy extents

    canv.setLineWidth(0.0)
    gm = GerberMachine("", canv, verbose=verbose)
    gm.Initialize()
    ResetExtents()
    
    # Render copper layer (light gray)
    if f_copper:
        gm.setColors(colors.Color(0.85, 0.85, 0.85), colors.Color(0, 0, 0))
        gm.ProcessFile(f_copper)
    
    # Render silkscreen overlay (darker gray)
    extents = None
    if f_overlay:
        gm.setColors(colors.Color(0.5, 0.5, 0.5), colors.Color(0, 0, 0))
        extents = gm.ProcessFile(f_overlay)
    
    return extents if extents else (0, 0, 100, 100)
    
    return extents

def producePrintoutsForLayer(base_name, layer, canv, pf=None, verbose=False):
    """Produce printouts for a specific layer with Gerber background"""
    global gerberPageSize, gerberMargin, gerberScale, gerberOffset, gerber_extents

    print(f"\nProcessing layer: {layer}")
    
    # Create temporary canvas to get extents
    from reportlab.pdfgen import canvas as temp_canvas
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
        temp_name = tmp_file.name
    
    try:
        ctmp = temp_canvas.Canvas(temp_name)
        ext = renderGerber(base_name, layer, ctmp, verbose=verbose)
        ctmp.save()
        
        # Calculate scale and offset to fit page, reserving space for table
        if ext and ext[0] != float('inf'):
            # Reserve space for the table (estimate table height based on number of components)
            # Assume max 6 components per page + header = 7 rows * 6mm + 8mm header = 50mm
            table_space = 60 * mm  # Reserve 60mm for table
            
            available_width = gerberPageSize[0] - 2 * gerberMargin
            available_height = gerberPageSize[1] - 2 * gerberMargin - table_space
            
            scale1 = available_width / (ext[2] - ext[0])
            scale2 = available_height / (ext[3] - ext[1])
            scale = min(scale1, scale2)
            gerberScale = (scale, scale)
            
            # Center the PCB in the available space (below the table)
            pcb_width = (ext[2] - ext[0]) * scale
            pcb_height = (ext[3] - ext[1]) * scale
            
            # Position PCB centered horizontally, and in the bottom portion (below table)
            offset_x = (gerberPageSize[0] - pcb_width) / 2 - ext[0] * scale
            offset_y = (available_height - pcb_height) / 2 + gerberMargin - ext[1] * scale
            
            gerberOffset = (offset_x, offset_y)
            
            print(f"Gerber extents: ({ext[0]:.2f}, {ext[1]:.2f}) to ({ext[2]:.2f}, {ext[3]:.2f})")
            print(f"Scale: {scale:.3f}, Offset: ({gerberOffset[0]/mm:.2f}, {gerberOffset[1]/mm:.2f}) mm")
        else:
            print("Warning: Could not determine Gerber extents, using default scaling")
            gerberScale = (1.0, 1.0)
            gerberOffset = (50 * mm, 50 * mm)
    
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_name)
        except:
            pass

    # Use provided pick and place data or load from CSV
    if pf is None:
        pf = PickAndPlaceFileKicad(base_name + ".CSV")
    
    ngrp = pf.num_groups(layer)
    print(f"Found {ngrp} component groups in {layer} layer")

    # Generate pages
    for page in range(0, (ngrp + 5) // 6):
        n_comps = min(6, ngrp - page * 6)
        print(f"Processing page {page + 1} with {n_comps} component groups")

        # Save canvas state and apply transformations
        canv.saveState()
        canv.translate(gerberOffset[0], gerberOffset[1])
        
        if layer == "Bottom":
            # For bottom layer, might need to mirror
            canv.scale(gerberScale[0], gerberScale[1])
        else:
            canv.scale(gerberScale[0], gerberScale[1])

        # Render Gerber background
        renderGerber(base_name, layer, canv, verbose=verbose)
        
        # Draw component overlay
        pf.draw(layer, page * 6, n_comps, canv)

        # Restore canvas state
        canv.restoreState()
        
        # Generate component table
        pf.gen_table(layer, page * 6, n_comps, canv)
        canv.showPage()

def main():
    if len(sys.argv) < 2:
        print("Usage: assygen <base_name>")
        print("Example: assygen freewatch")
        sys.exit(1)
    
    # Get base_name, ignoring any flags
    base_name = None
    use_separate_pos = False
    verbose = False
    
    # First pass: look for flags
    for arg in sys.argv[1:]:
        if arg == "--separate-pos":
            use_separate_pos = True
        elif arg == "--verbose":
            verbose = True
    
    # Second pass: get base_name (first non-flag argument)
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            base_name = arg
            break
    
    if not base_name:
        print("Usage: assygen <base_name>")
        print("Example: assygen freewatch")
        sys.exit(1)
    
    # Create the appropriate pick-and-place loader
    if use_separate_pos:
        print("Using separate .pos files")
        pf = PickAndPlaceFileSeparate(base_name)
    else:
        print("Using combined CSV file")
        # Try to find the CSV file
        csv_file = None
        csv_candidates = [base_name + ".CSV", base_name + ".csv"]
        for candidate in csv_candidates:
            if os.path.exists(candidate):
                csv_file = candidate
                break
        
        if csv_file:
            pf = PickAndPlaceFileKicad(csv_file) 
        else:
            print("Error: No CSV file found, but separate .pos files were not detected")
            sys.exit(1)
    
    # Determine optimal page orientation based on PCB dimensions
    print("\nAnalyzing PCB dimensions for optimal orientation...")
    pcb_extents = get_pcb_extents(base_name, verbose=verbose)
    optimal_pagesize = determine_optimal_orientation(pcb_extents)
    
    # Update global gerberPageSize for consistent use throughout
    global gerberPageSize
    gerberPageSize = optimal_pagesize
    
    # Create PDF with full features
    canv = canvas.Canvas(base_name + "_assy.pdf", pagesize=gerberPageSize)
    
    try:
        # Process both top and bottom layers
        producePrintoutsForLayer(base_name, "Top", canv, pf, verbose=verbose) 
        producePrintoutsForLayer(base_name, "Bottom", canv, pf, verbose=verbose)
        canv.save()
        
        print(f"\nGenerated {base_name}_assy.pdf with Gerber backgrounds!")
        print("Contains assembly drawings for both Top and Bottom layers")
        
    except FileNotFoundError as e:
        print(f"Error: Required file not found - {e}")
        print("Make sure you have the following files:")
        if use_separate_pos:
            print(f"  - {base_name}-top.pos and/or {base_name}-bottom.pos (position files)")
        else:
            print(f"  - {base_name}.CSV (pick and place data)")
        print(f"  - {base_name}.GTL/.GBL or {base_name}-F_Cu.gbr/-B_Cu.gbr (copper layers)")  
        print(f"  - {base_name}.GTO/.GBO or {base_name}-F_Silkscreen.gbr/-B_Silkscreen.gbr (silkscreen layers)")
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: Permission denied - {e}")
        print("Make sure the output directory is writable and the PDF file is not open in another application.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
