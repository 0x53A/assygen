#!/usr/bin/env python3

from modern_gerber import GerberMachine, ResetExtents, gerber_extents, DrillFileParser
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter, landscape
import sys
import os
import tempfile
import re

class KiCadReportParser:
    """Parser for KiCad footprint report files (.rpt)
    
    Extracts exact component dimensions and footprint data from KiCad reports
    instead of guessing from footprint names.
    """
    
    def __init__(self):
        self.components = {}  # ref -> component data
        
    def parse_report_file(self, rpt_file_path):
        """Parse a KiCad .rpt file and extract component data"""
        try:
            with open(rpt_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (FileNotFoundError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read report file {rpt_file_path}: {e}")
            return
        
        # Split into modules
        modules = re.split(r'\$MODULE\s+(\w+)', content)[1:]  # Skip header
        
        # Process modules in pairs (ref, content)
        for i in range(0, len(modules), 2):
            if i + 1 < len(modules):
                ref = modules[i].strip()
                module_content = modules[i + 1]
                component_data = self._parse_module(ref, module_content)
                if component_data:
                    self.components[ref] = component_data
        
        print(f"Parsed {len(self.components)} components from report file")
    
    def _parse_module(self, ref, content):
        """Parse a single module section"""
        lines = content.split('\n')
        component_data = {
            'ref': ref,
            'footprint': '',
            'position': (0, 0),
            'orientation': 0,
            'layer': 'front',
            'pads': [],
            'bbox': (0, 0)  # width, height in mm
        }
        
        for line in lines:
            line = line.strip()
            
            # Parse footprint name
            if line.startswith('footprint '):
                component_data['footprint'] = line[10:].strip()
            
            # Parse component position and orientation
            elif line.startswith('position '):
                parts = line.split()
                try:
                    x = float(parts[1])
                    y = float(parts[2])
                    component_data['position'] = (x, y)
                    if 'orientation' in line:
                        orientation = float(parts[4])
                        component_data['orientation'] = orientation
                except (IndexError, ValueError):
                    pass
            
            # Parse layer
            elif line.startswith('layer '):
                component_data['layer'] = line[6:].strip()
            
            # Parse pad information  
            elif line.startswith('position ') and 'size' in line:
                # This is a pad position line with size info (not the component position which has 'orientation')
                # Format: position -0.775000  0.000000  size  0.900000  0.950000  orientation 0.00
                parts = line.split()
                try:
                    # parts[0] = 'position', parts[1] = x, parts[2] = y, parts[3] = 'size', parts[4] = w, parts[5] = h
                    pad_x = float(parts[1])
                    pad_y = float(parts[2])
                    size_idx = parts.index('size')
                    pad_w = float(parts[size_idx + 1])
                    pad_h = float(parts[size_idx + 2])
                    
                    component_data['pads'].append({
                        'position': (pad_x, pad_y),
                        'size': (pad_w, pad_h)
                    })
                except (IndexError, ValueError) as e:
                    pass
        
        # Calculate component bounding box from pads
        if component_data['pads']:
            component_data['bbox'] = self._calculate_bbox(component_data['pads'])
        
        return component_data
    
    def _calculate_bbox(self, pads):
        """Calculate component bounding box from pad positions and sizes"""
        if not pads:
            return (2.0, 1.0)  # Default size
        
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')
        
        for pad in pads:
            pad_x, pad_y = pad['position']
            pad_w, pad_h = pad['size']
            
            # Calculate pad extents
            left = pad_x - pad_w / 2
            right = pad_x + pad_w / 2
            bottom = pad_y - pad_h / 2
            top = pad_y + pad_h / 2
            
            min_x = min(min_x, left)
            max_x = max(max_x, right)
            min_y = min(min_y, bottom)
            max_y = max(max_y, top)
        
        pad_width = max_x - min_x
        pad_height = max_y - min_y
        
        # Estimate component body size from pad layout
        # For 2-pad components (resistors, capacitors), body is typically larger than pad span
        if len(pads) == 2:
            # Component body is typically 1.2-1.5x the pad span for standard SMD components
            body_width = max(pad_width * 1.3, pad_width + 0.4)  # At least 0.4mm larger than pads
            body_height = max(pad_height * 1.5, pad_height + 0.6)  # At least 0.6mm larger than pads
        else:
            # Multi-pad components: use pad envelope with reasonable margin
            body_width = pad_width + 0.5   # 0.5mm margin beyond pads
            body_height = pad_height + 0.5  # 0.5mm margin beyond pads
        
        return (body_width, body_height)
    
    def get_component_dimensions(self, ref):
        """Get component dimensions for a reference designator"""
        if ref in self.components:
            bbox = self.components[ref]['bbox']
            return bbox, True  # Return dimensions and exact=True
        else:
            # Fallback to default size if not found in report
            return (2.0, 1.0), False  # Return dimensions and exact=False
    
    def get_component_data(self, ref):
        """Get full component data for a reference designator"""
        return self.components.get(ref, None)

# Global variables for gerber rendering
gerberPageSize = letter
gerberMargin = 0.75 * 25.4 * mm  # 0.75 inch margin
gerberScale = (1.0, 1.0)
gerberOffset = (0.0, 0.0)

def parse_component_dimensions(package_name):
    """Parse component dimensions from KiCad footprint names
    
    Returns (width_mm, height_mm) based on package name.
    Falls back to default size if parsing fails.
    """
    import re
    
    # Default fallback size
    default_w, default_h = 2.0, 1.0  # 2mm x 1mm default
    
    try:
        # Handle metric footprint names (most common)
        # Examples: C_0603_1608Metric, R_0805_2012Metric, etc.
        # The format is: _[imperial_size]_[metric_size]Metric
        # Where metric_size is LLWW meaning L.L mm x W.W mm (Length x Width)
        # For rectangular components, length is typically the longer dimension
        metric_match = re.search(r'_\d{4}_(\d{4})Metric', package_name)
        if metric_match:
            # Extract metric dimensions (e.g., 1608 = 1.6mm x 0.8mm)
            metric_code = metric_match.group(1)
            # First two digits = length in 0.1mm, last two digits = width in 0.1mm  
            length_mm = int(metric_code[:2]) / 10.0
            width_mm = int(metric_code[2:]) / 10.0
            # Return width first, then length (W x L instead of L x W)
            # This matches the typical component orientation in pick-and-place
            return (width_mm, length_mm)
        
        # Handle standard imperial sizes with metric conversion
        # Examples: 0603, 0805, 1206, etc.
        imperial_match = re.search(r'_?(\d{4})(?:[_\-]|$)', package_name)
        if imperial_match:
            size_code = imperial_match.group(1)
            # Standard component size lookup table (imperial to metric)
            size_map = {
                '0201': (0.6, 0.3),   # 0201: 0.6mm x 0.3mm
                '0402': (1.0, 0.5),   # 0402: 1.0mm x 0.5mm  
                '0603': (1.6, 0.8),   # 0603: 1.6mm x 0.8mm
                '0805': (2.0, 1.25),  # 0805: 2.0mm x 1.25mm
                '1206': (3.2, 1.6),   # 1206: 3.2mm x 1.6mm
                '1210': (3.2, 2.5),   # 1210: 3.2mm x 2.5mm
                '2010': (5.0, 2.5),   # 2010: 5.0mm x 2.5mm
                '2512': (6.35, 3.2),  # 2512: 6.35mm x 3.2mm
            }
            if size_code in size_map:
                return size_map[size_code]
        
        # Handle special formats like CAPAE530X550N (5.3mm x 5.5mm)
        cap_match = re.search(r'CAPAE(\d{3})X(\d{3})', package_name)
        if cap_match:
            w_mm = int(cap_match.group(1)) / 100.0
            h_mm = int(cap_match.group(2)) / 100.0
            return (w_mm, h_mm)
        
        # Handle SOT packages (TO packages)
        if 'SOT' in package_name or 'TO-' in package_name:
            if 'SOT-23' in package_name:
                return (2.9, 1.3)  # SOT-23: 2.9mm x 1.3mm
            elif 'SOT-89' in package_name:
                return (4.5, 2.5)  # SOT-89: 4.5mm x 2.5mm
            else:
                return (3.0, 2.0)  # Generic SOT package
        
        # Handle QFP/QFN packages - extract from names like QFP-48_7x7mm
        qfp_match = re.search(r'QF[PN]-\d+_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm', package_name)
        if qfp_match:
            w_mm = float(qfp_match.group(1))
            h_mm = float(qfp_match.group(2))
            return (w_mm, h_mm)
        
        # Handle BGA packages - extract from names like BGA-256_17x17mm
        bga_match = re.search(r'BGA-\d+_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm', package_name)
        if bga_match:
            w_mm = float(bga_match.group(1))
            h_mm = float(bga_match.group(2))
            return (w_mm, h_mm)
            
        # Handle connector packages
        if 'USB' in package_name.upper():
            if 'MICRO' in package_name.upper():
                return (5.0, 2.5)  # USB Micro: ~5mm x 2.5mm
            else:
                return (8.0, 4.0)  # Standard USB: ~8mm x 4mm
        
        if 'CONN' in package_name.upper():
            return (5.0, 2.0)  # Generic connector
            
        # Handle LED packages
        if 'LED' in package_name.upper():
            if '0603' in package_name:
                return (1.6, 0.8)  # 0603 LED
            elif '0805' in package_name:
                return (2.0, 1.25)  # 0805 LED
            else:
                return (3.0, 1.5)  # Generic LED
        
        # Handle crystal/oscillator packages
        if any(x in package_name.upper() for x in ['CRYSTAL', 'OSC', 'XTAL']):
            if '3225' in package_name:
                return (3.2, 2.5)  # 3.2mm x 2.5mm crystal
            elif '5032' in package_name:
                return (5.0, 3.2)  # 5.0mm x 3.2mm crystal
            else:
                return (4.0, 2.5)  # Generic crystal
        
        # Handle inductor packages (similar to capacitors but often larger)
        if 'IND' in package_name.upper() or 'L_' in package_name:
            if '0603' in package_name:
                return (1.6, 0.8)
            elif '0805' in package_name:
                return (2.0, 1.25)
            elif '1206' in package_name:
                return (3.2, 1.6)
            else:
                return (3.0, 3.0)  # Generic inductor (often square)
    
    except (ValueError, AttributeError):
        pass
    
    # Return default if no pattern matches
    return (default_w, default_h)

class PPComponent:
    def __init__(self, xc, yc, w, h, name, desc, ref, rotation=0.0, exact_dimensions=False):
        self.xc = xc
        self.yc = yc
        self.w = w
        self.h = h
        self.rotation = rotation  # Store rotation for proper rendering
        self.exact_dimensions = exact_dimensions  # Flag to indicate if dimensions are from KiCad report
        
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
        exact_count = 0
        cross_count = 0
        
        for i in parts:
            # Set colors with transparency (alpha = 0.6 for 60% opacity)
            # Use modulo to wrap around when there are more component groups than colors
            color_index = n % len(self.col_map)
            stroke_color = self.col_map[color_index]
            fill_color = self.col_map[color_index]
            
            canv.setStrokeColorRGB(stroke_color.red, stroke_color.green, stroke_color.blue, alpha=0.8)
            canv.setFillColorRGB(fill_color.red, fill_color.green, fill_color.blue, alpha=0.6)
            n = n + 1
            for j in i:
                # Draw rotated component
                canv.saveState()
                canv.translate(j.xc, j.yc)  # Move to component center
                canv.rotate(j.rotation - 90)  # Apply rotation with 90° correction
                
                if j.exact_dimensions:
                    # Draw rectangle for components with exact dimensions
                    canv.rect(-j.w/2, -j.h/2, j.w, j.h, 1, 1)
                    exact_count += 1
                else:
                    # Draw X for components with estimated dimensions
                    cross_size = max(j.w, j.h) / 4  # Half the size (divide by 4 instead of 2)
                    # Apply sanity check: min 1mm, max 4mm (creates 2x2mm to 8x8mm crosses)
                    cross_size = max(1.0, min(4.0, cross_size))
                    # Track cross sizes for summary
                    if not hasattr(self, 'cross_sizes'):
                        self.cross_sizes = []
                    self.cross_sizes.append(cross_size)
                    canv.setLineWidth(0.5)  # Keep bold line width
                    # Draw diagonal lines to form an X
                    canv.line(-cross_size, -cross_size, cross_size, cross_size)  # Top-left to bottom-right
                    canv.line(-cross_size, cross_size, cross_size, -cross_size)  # Bottom-left to top-right
                    cross_count += 1
                
                canv.restoreState()
        
        print(f"Drew {exact_count} rectangles (exact) and {cross_count} crosses (estimated)")
        
        # Print cross size summary if we have crosses
        if hasattr(self, 'cross_sizes') and self.cross_sizes:
            min_cross = min(self.cross_sizes)
            max_cross = max(self.cross_sizes)
            avg_cross = sum(self.cross_sizes) / len(self.cross_sizes)
            print(f"Cross sizes: min={min_cross:.2f}mm, max={max_cross:.2f}mm, avg={avg_cross:.2f}mm")
    
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
            
            # Use modulo to wrap around when there are more component groups than colors
            color_index = n % len(self.col_map)
            canv.setFillColor(self.col_map[color_index])
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
    def __init__(self, fname, report_parser=None):
        print("Loading pick and place file:", fname)
        
        self.report_parser = report_parser  # Store reference to report parser
        
        self.col_map = [colors.Color(1,0,0), 
                       colors.Color(1,0.5,0), 
                       colors.Color(0,1,0), 
                       colors.Color(0.6,0.3,0.1), 
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
        
        # Try to find rotation column (optional)
        try:
            i_rot = header.index("Rot")
        except ValueError:
            i_rot = None

        self.layers = {}
        self.layers["Top"] = {}        
        self.layers["Bottom"] = {}
       
        print(f"Column indices - Ref: {i_dsg}, Val: {i_desc}, PosX: {i_cx}, PosY: {i_cy}")
        
        for row in rows[1:]:
            if len(row) > 0:
                cx = float(row[i_cx]) * mm
                cy = float(row[i_cy]) * mm

                # Get rotation if available
                rotation = 0.0
                if i_rot is not None and len(row) > i_rot:
                    try:
                        rotation = float(row[i_rot])
                    except (ValueError, IndexError):
                        rotation = 0.0

                # Parse component dimensions from package name if available
                exact_dimensions = False  # Track if dimensions are exact
                if len(row) > 2:  # Check if Package column exists
                    try:
                        package_col_idx = header.index("Package")
                        package_name = row[package_col_idx]
                        
                        # Try to get dimensions from report parser first
                        if self.report_parser:
                            (w_mm, h_mm), exact_dimensions = self.report_parser.get_component_dimensions(row[i_dsg])
                        else:
                            # Fallback to name-based parsing
                            w_mm, h_mm = parse_component_dimensions(package_name)
                            exact_dimensions = False  # Name-based parsing is estimated
                        
                        w = w_mm * mm
                        h = h_mm * mm
                    except (ValueError, IndexError):
                        # Fallback to default size if Package column missing or parsing fails
                        w = 1 * mm
                        h = 1 * mm
                        exact_dimensions = False
                else:
                    w = 1 * mm
                    h = 1 * mm
                    exact_dimensions = False
                    
                l = row[i_layer]
                if l == "F.Cu":
                    layer = "Top"
                else:
                    layer = "Bottom"
                    
                ref = row[i_desc]
                if ref not in self.layers[layer]:
                    self.layers[layer][ref] = []
                self.layers[layer][ref].append(PPComponent(cx, cy, w, h, row[i_dsg], row[i_desc], ref, rotation, exact_dimensions))

class PickAndPlaceFileSeparate(PickAndPlaceFile):
    """Handle separate .pos files for top and bottom layers"""
    def __init__(self, base_name, report_parser=None):
        import os
        
        self.report_parser = report_parser  # Store reference to report parser
        
        self.col_map = [colors.Color(1,0,0), 
                       colors.Color(1,0.5,0), 
                       colors.Color(0,1,0), 
                       colors.Color(0.6,0.3,0.1), 
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
                    
                    # Parse component dimensions - try report parser first
                    exact_dimensions = False  # Track if dimensions are exact
                    if self.report_parser:
                        (w_mm, h_mm), exact_dimensions = self.report_parser.get_component_dimensions(ref)
                    else:
                        # Fallback to name-based parsing
                        w_mm, h_mm = parse_component_dimensions(package)
                        exact_dimensions = False  # Name-based parsing is estimated
                    
                    w = w_mm * mm
                    h = h_mm * mm
                    
                    if val not in self.layers[layer]:
                        self.layers[layer][val] = []
                    self.layers[layer][val].append(PPComponent(cx, cy, w, h, ref, val, val, rotation, exact_dimensions))
                    
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

def find_drill_files(base_name):
    """Find drill files using KiCad naming conventions"""
    import os
    
    # Check for newer KiCad format with separate PTH/NPTH files
    pth_file = base_name + "-PTH.drl"    # Plated Through Holes
    npth_file = base_name + "-NPTH.drl"  # Non-Plated Through Holes
    
    # Check for older single drill file format
    single_drill = base_name + ".drl"
    
    drill_files = []
    
    if os.path.exists(pth_file):
        drill_files.append(pth_file)
    if os.path.exists(npth_file):
        drill_files.append(npth_file)
    if os.path.exists(single_drill) and not drill_files:  # Only use single file if no PTH/NPTH files
        drill_files.append(single_drill)
    
    return drill_files

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
    
    # Also check drill files for extents
    drill_files = find_drill_files(base_name)
    if drill_files:
        for drill_file in drill_files:
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                temp_name = tmp_file.name
            
            try:
                ctmp = temp_canvas.Canvas(temp_name)
                drill_parser = DrillFileParser(ctmp, verbose=verbose)
                extents = drill_parser.process_file(drill_file)
                if extents and extents[0] != float('inf'):
                    all_extents.append(extents)
                ctmp.save()
            finally:
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
    
    # Render drill holes (white holes with black outlines)
    drill_files = find_drill_files(base_name)
    if drill_files:
        for drill_file in drill_files:
            drill_parser = DrillFileParser(canv, verbose=verbose)
            drill_parser.process_file(drill_file)
            drill_parser.render_holes()
    
    return extents if extents else (0, 0, 100, 100)

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
        pf = PickAndPlaceFileKicad(base_name + ".CSV", None)  # No report parser in this fallback case
    
    ngrp = pf.num_groups(layer)
    print(f"Found {ngrp} component groups in {layer} layer")

    # Generate pages with new layout:
    # Page 1: Table with ALL components
    # Page 2: Single drawing with ALL components
    # Page 3+: Current paginated approach (6 components per page)
    
    if ngrp > 0:
        # Page 1: Complete component table
        print(f"Processing page 1: Complete component table ({ngrp} component groups)")
        pf.gen_table(layer, 0, ngrp, canv)
        canv.showPage()
        
        # Page 2: Complete assembly drawing with all components
        print(f"Processing page 2: Complete assembly drawing with all components")
        
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
        
        # Draw ALL components
        pf.draw(layer, 0, ngrp, canv)

        # Restore canvas state
        canv.restoreState()
        canv.showPage()
    
    # Pages 3+: Traditional 6-components-per-page approach
    for page in range(0, (ngrp + 5) // 6):
        n_comps = min(6, ngrp - page * 6)
        print(f"Processing page {page + 3} with {n_comps} component groups")

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
    
    # Try to load KiCad report file for accurate component dimensions
    report_parser = None
    report_file = base_name + ".rpt"
    if os.path.exists(report_file):
        print(f"Found KiCad report file: {report_file}")
        report_parser = KiCadReportParser()
        report_parser.parse_report_file(report_file)
    else:
        print(f"No report file found ({report_file}), using fallback dimension parsing")
    
    if use_separate_pos:
        print("Using separate .pos files")
        pf = PickAndPlaceFileSeparate(base_name, report_parser)
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
            pf = PickAndPlaceFileKicad(csv_file, report_parser) 
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
