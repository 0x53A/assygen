#!/usr/bin/env python3
"""
Modern Gerber file parser for Python 3
Replaces the plex-based parser with a simpler regex-based approach
"""

import re
import math
from reportlab.lib.units import mm, inch
from reportlab.lib import colors

class GerberAperture:
    """Represents a Gerber aperture (tool definition)"""
    def __init__(self, aperture_id, shape, params):
        self.id = aperture_id
        self.shape = shape  # 'C' for circle, 'R' for rectangle, etc.
        self.params = params  # list of dimensions
        
    def draw_flash(self, canvas, x, y):
        """Draw this aperture as a flash at the given coordinates"""
        if self.shape == 'C':  # Circle
            radius = self.params[0] / 2
            canvas.circle(x, y, radius, stroke=0, fill=1)
        elif self.shape == 'R':  # Rectangle
            w, h = self.params[0], self.params[1]
            canvas.rect(x - w/2, y - h/2, w, h, stroke=0, fill=1)

class GerberExtents:
    """Track the extents of the Gerber drawing"""
    def __init__(self):
        self.reset()
    
    def reset(self):
        self.xmin = float('inf')
        self.ymin = float('inf') 
        self.xmax = float('-inf')
        self.ymax = float('-inf')
    
    def update(self, x, y, aperture=None):
        # Add some margin for aperture size
        margin = 0
        if aperture and aperture.shape == 'C':
            margin = aperture.params[0] / 2
        elif aperture and aperture.shape == 'R':
            margin = max(aperture.params[0], aperture.params[1]) / 2
            
        self.xmin = min(self.xmin, x - margin)
        self.ymin = min(self.ymin, y - margin)
        self.xmax = max(self.xmax, x + margin)
        self.ymax = max(self.ymax, y + margin)
    
    def get_bounds(self):
        return (self.xmin, self.ymin, self.xmax, self.ymax)

class ModernGerberParser:
    """Modern Gerber parser using regex instead of plex"""
    
    def __init__(self, canvas=None):
        self.canvas = canvas
        self.apertures = {}
        self.current_aperture = None
        self.current_x = 0
        self.current_y = 0
        self.extents = GerberExtents()
        self.format_spec = {'x_digits': 4, 'y_digits': 4, 'decimal_places': 6}
        self.unit_scale = mm  # Default to mm
        self.fg_color = colors.black
        self.bg_color = colors.white
        
        # Regex patterns for Gerber commands
        self.patterns = {
            'format': re.compile(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%'),
            'units': re.compile(r'%MO(MM|IN)\*%'),
            'aperture_def': re.compile(r'%ADD(\d+)([CR]),([0-9.X]+)\*%'),
            'aperture_select': re.compile(r'D(\d+)\*'),
            'coordinate': re.compile(r'X(-?\d+)Y(-?\d+)D(\d+)\*'),
            'x_only': re.compile(r'X(-?\d+)D(\d+)\*'),
            'y_only': re.compile(r'Y(-?\d+)D(\d+)\*'),
            'comment': re.compile(r'G04.*\*'),
            'end': re.compile(r'M02\*'),
        }
    
    def set_colors(self, fg_color, bg_color):
        """Set foreground and background colors"""
        self.fg_color = fg_color
        self.bg_color = bg_color
        if self.canvas:
            self.canvas.setFillColor(fg_color)
            self.canvas.setStrokeColor(fg_color)
    
    def parse_coordinate(self, coord_str):
        """Parse coordinate string according to format specification"""
        # Convert string to number with proper decimal placement
        coord_int = int(coord_str)
        # Assume format is implicit decimal places
        return coord_int / (10 ** self.format_spec['decimal_places']) * self.unit_scale
    
    def process_file(self, filename):
        """Process a Gerber file"""
        print(f"Processing Gerber file: {filename}")
        
        try:
            with open(filename, 'r') as f:
                content = f.read()
        except FileNotFoundError:
            print(f"Warning: Gerber file {filename} not found - skipping")
            return self.extents.get_bounds()
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            return self.extents.get_bounds()
        
        # Split into lines and process each
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
                
            try:
                self._process_line(line)
            except Exception as e:
                print(f"Error processing line {line_num}: {line}")
                print(f"Error: {e}")
                continue
        
        bounds = self.extents.get_bounds()
        print(f"Gerber extents: ({bounds[0]:.2f}, {bounds[1]:.2f}) to ({bounds[2]:.2f}, {bounds[3]:.2f})")
        return bounds
    
    def _process_line(self, line):
        """Process a single line of Gerber code"""
        
        # Check for format specification
        match = self.patterns['format'].match(line)
        if match:
            self.format_spec = {
                'x_digits': int(match.group(1)) + int(match.group(2)),
                'y_digits': int(match.group(3)) + int(match.group(4)),
                'decimal_places': int(match.group(2))  # fractional digits
            }
            return
        
        # Check for units
        match = self.patterns['units'].match(line)
        if match:
            if match.group(1) == 'MM':
                self.unit_scale = mm
            else:
                self.unit_scale = inch
            return
        
        # Check for aperture definition
        match = self.patterns['aperture_def'].match(line)
        if match:
            aperture_id = int(match.group(1))
            shape = match.group(2)
            params_str = match.group(3)
            
            # Parse parameters
            if 'X' in params_str:
                params = [float(x) * self.unit_scale for x in params_str.split('X')]
            else:
                params = [float(params_str) * self.unit_scale]
            
            self.apertures[aperture_id] = GerberAperture(aperture_id, shape, params)
            return
        
        # Check for aperture selection
        match = self.patterns['aperture_select'].match(line)
        if match:
            aperture_id = int(match.group(1))
            self.current_aperture = self.apertures.get(aperture_id)
            return
        
        # Check for coordinate with operation
        match = self.patterns['coordinate'].match(line)
        if match:
            x = self.parse_coordinate(match.group(1))
            y = self.parse_coordinate(match.group(2))
            operation = int(match.group(3))
            
            self._execute_operation(x, y, operation)
            return
        
        # Check for X-only coordinate
        match = self.patterns['x_only'].match(line)
        if match:
            x = self.parse_coordinate(match.group(1))
            operation = int(match.group(2))
            self._execute_operation(x, self.current_y, operation)
            return
        
        # Check for Y-only coordinate  
        match = self.patterns['y_only'].match(line)
        if match:
            y = self.parse_coordinate(match.group(1))
            operation = int(match.group(2))
            self._execute_operation(self.current_x, y, operation)
            return
        
        # Ignore comments and other commands for now
        if self.patterns['comment'].match(line) or self.patterns['end'].match(line):
            return
        
        # Ignore unrecognized commands (for now)
        if line.startswith('G') or line.startswith('%') or line.startswith('D'):
            return
    
    def _execute_operation(self, x, y, operation):
        """Execute a drawing operation"""
        if operation == 1:  # Move (interpolate) - draw line
            if self.canvas and self.current_aperture:
                # Draw line from current position to new position
                self._draw_line(self.current_x, self.current_y, x, y)
            self.extents.update(x, y, self.current_aperture)
        
        elif operation == 2:  # Move (without drawing)
            pass  # Just update position
        
        elif operation == 3:  # Flash (place aperture)
            if self.canvas and self.current_aperture:
                self.current_aperture.draw_flash(self.canvas, x, y)
            self.extents.update(x, y, self.current_aperture)
        
        # Update current position
        self.current_x = x
        self.current_y = y
    
    def _draw_line(self, x1, y1, x2, y2):
        """Draw a line using the current aperture"""
        if not self.current_aperture or not self.canvas:
            return
        
        # For rectangular apertures, draw as a filled rectangle along the path
        if self.current_aperture.shape == 'R':
            width = self.current_aperture.params[0]
            # Calculate line path and draw rectangle
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx*dx + dy*dy)
            
            if length > 0:
                # Draw as rectangle along the line
                self.canvas.saveState()
                angle = math.atan2(dy, dx) * 180 / math.pi
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                self.canvas.translate(center_x, center_y)
                self.canvas.rotate(angle)
                self.canvas.rect(-length/2, -width/2, length, width, stroke=0, fill=1)
                self.canvas.restoreState()
        
        elif self.current_aperture.shape == 'C':
            # For circular apertures, draw as line with round caps
            width = self.current_aperture.params[0]
            self.canvas.setLineWidth(width)
            self.canvas.line(x1, y1, x2, y2)
        
        # Update extents for the line
        self.extents.update(x1, y1, self.current_aperture)
        self.extents.update(x2, y2, self.current_aperture)

# Global variables for compatibility with original code
gerber_extents = [0, 0, 0, 0]

def ResetExtents():
    """Reset global extents (for compatibility)"""
    global gerber_extents
    gerber_extents = [float('inf'), float('inf'), float('-inf'), float('-inf')]

def UpdateExtents(x1, y1, x2, y2):
    """Update global extents (for compatibility)"""
    global gerber_extents
    gerber_extents[0] = min(gerber_extents[0], min(x1, x2))
    gerber_extents[1] = min(gerber_extents[1], min(y1, y2))
    gerber_extents[2] = max(gerber_extents[2], max(x1, x2))
    gerber_extents[3] = max(gerber_extents[3], max(y1, y2))

# Compatibility class that mimics the original GerberMachine interface
class GerberMachine:
    def __init__(self, filename, canvas):
        self.parser = ModernGerberParser(canvas)
        self.canvas = canvas
    
    def Initialize(self):
        pass
    
    def setColors(self, fg_color, bg_color):
        self.parser.set_colors(fg_color, bg_color)
    
    def ProcessFile(self, filename):
        bounds = self.parser.process_file(filename)
        # Update global extents for compatibility
        global gerber_extents
        if bounds[0] != float('inf'):  # Valid bounds
            gerber_extents = list(bounds)
        return bounds

if __name__ == "__main__":
    # Test the parser
    import sys
    from reportlab.pdfgen import canvas
    
    if len(sys.argv) > 1:
        c = canvas.Canvas("test_gerber.pdf")
        parser = ModernGerberParser(c)
        bounds = parser.process_file(sys.argv[1])
        print(f"Processed file with bounds: {bounds}")
        c.save()
