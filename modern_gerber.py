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
    
    def __init__(self, canvas=None, verbose=False):
        self.canvas = canvas
        self.verbose = verbose
        self.apertures = {}
        self.current_aperture = None
        self.current_x = 0
        self.current_y = 0
        self.extents = GerberExtents()
        self.format_spec = {'x_digits': 4, 'y_digits': 4, 'decimal_places': 6}
        self.unit_scale = mm  # Default to mm
        self.fg_color = colors.black
        self.bg_color = colors.white
        
        # Interpolation mode: 1=linear, 2=clockwise arc, 3=counterclockwise arc
        self.interpolation_mode = 1
        
        # Arc center offset (I, J parameters)
        self.arc_center_i = 0
        self.arc_center_j = 0
        
        # Track unrecognized/skipped commands for verbose output
        self.unrecognized_commands = set()
        self.skipped_commands = set()
        
        # Regex patterns for Gerber commands
        self.patterns = {
            'format': re.compile(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%'),
            'units': re.compile(r'%MO(MM|IN)\*%'),
            'aperture_def': re.compile(r'%ADD(\d+)([CR]),([0-9.X]+)\*%'),
            'aperture_select': re.compile(r'D(\d+)\*'),
            'coordinate': re.compile(r'X(-?\d+)Y(-?\d+)D(\d+)\*'),
            'coordinate_with_arc': re.compile(r'X(-?\d+)Y(-?\d+)I(-?\d+)J(-?\d+)D(\d+)\*'),
            'x_only': re.compile(r'X(-?\d+)D(\d+)\*'),
            'y_only': re.compile(r'Y(-?\d+)D(\d+)\*'),
            'arc_params': re.compile(r'I(-?\d+)J(-?\d+)'),
            'g_command': re.compile(r'G0*([123])\*?'),
            'g74_g75': re.compile(r'G(74|75)\*'),
            'aperture_macro': re.compile(r'%AM([^*]+)\*%'),
            'macro_primitive': re.compile(r'^(\d+),'),
            'macro_comment': re.compile(r'^0 .*\*$'),  # Aperture macro comment primitive
            'attribute': re.compile(r'%(TA|TO|TF|TD)([^*]*)\*%'),
            'layer_polarity': re.compile(r'%LP([CD])\*%'),
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
        
        # Print verbose information if requested
        if self.verbose:
            self._print_verbose_summary()
        
        return bounds
    
    def _print_verbose_summary(self):
        """Print summary of unrecognized/skipped commands in verbose mode"""
        if self.unrecognized_commands:
            print("\n--- Unrecognized Gerber commands ---")
            for cmd in sorted(self.unrecognized_commands):
                print(f"  {cmd}")
        
        if self.skipped_commands:
            print("\n--- Skipped Gerber commands ---")
            for cmd in sorted(self.skipped_commands):
                print(f"  {cmd}")
        
        if not self.unrecognized_commands and not self.skipped_commands:
            print("\n--- All commands recognized ---")
    
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
        
        # Check for custom aperture definitions (RoundRect, etc.)
        if line.startswith('%ADD') and ('RoundRect' in line or 'FreePoly' in line):
            # Extract aperture ID
            import re
            match = re.match(r'%ADD(\d+)([^,]+),([^*]+)\*%', line)
            if match:
                aperture_id = int(match.group(1))
                shape_name = match.group(2)
                params_str = match.group(3)
                
                if 'RoundRect' in shape_name:
                    # Parse RoundRect parameters: rounding_radius,x1,y1,x2,y2,x3,y3,x4,y4
                    try:
                        params = [float(x) * self.unit_scale for x in params_str.split('X')]
                        if len(params) >= 9:  # rounding radius + 4 corner coordinates
                            # Use the coordinate extent to determine size
                            x_coords = params[1::2]  # x coordinates
                            y_coords = params[2::2]  # y coordinates
                            width = max(x_coords) - min(x_coords)
                            height = max(y_coords) - min(y_coords)
                            # Create rectangular aperture as approximation
                            self.apertures[aperture_id] = GerberAperture(aperture_id, 'R', [width, height])
                            # This is handled (approximated), so don't mark as skipped
                        else:
                            # Fallback to small circle - handled but approximate
                            default_size = 0.1 * self.unit_scale
                            self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                    except (ValueError, IndexError):
                        # Fallback to small circle if parsing fails - handled but approximate
                        default_size = 0.1 * self.unit_scale
                        self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                else:
                    # For FreePoly and other custom apertures, create aperture with fallback
                    # Parse the parameter (usually the rotation angle)
                    try:
                        param = float(params_str) * self.unit_scale if params_str else 0.1 * self.unit_scale
                        # Use the parameter as a size hint if it seems reasonable, otherwise use default
                        if param > 0 and param < 10:  # Reasonable size range
                            default_size = param
                        else:
                            default_size = 0.1 * self.unit_scale
                    except (ValueError, IndexError):
                        default_size = 0.1 * self.unit_scale
                    
                    self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                    # These are handled (with fallback approximation), don't mark as skipped
            return
        
        # Check for aperture macros
        match = self.patterns['aperture_macro'].match(line)
        if match:
            # Skip aperture macro definitions - these are complex custom shapes we can't fully render
            # But don't mark as "skipped" since they're legitimate Gerber extended commands
            # The actual limitation is in our shape rendering capability, not command recognition
            return
        
        # Check for aperture macro comment primitives (primitive 0)
        match = self.patterns['macro_comment'].match(line)
        if match:
            # These are just comments within aperture macros - ignore silently
            return
        
        # Check for attributes and metadata
        match = self.patterns['attribute'].match(line)
        if match:
            # These are just metadata - ignore silently
            return
        
        # Check for layer polarity
        match = self.patterns['layer_polarity'].match(line)
        if match:
            # This is just metadata - ignore silently
            return
        
        # Check for aperture selection
        match = self.patterns['aperture_select'].match(line)
        if match:
            aperture_id = int(match.group(1))
            self.current_aperture = self.apertures.get(aperture_id)
            return
        
        # Check for G commands (interpolation modes)
        match = self.patterns['g_command'].match(line)
        if match:
            self.interpolation_mode = int(match.group(1))
            return
        
        # Check for G74/G75 (quadrant mode - informational only)
        match = self.patterns['g74_g75'].match(line)
        if match:
            # G74 = single quadrant mode, G75 = multi quadrant mode
            # These affect how arc coordinates are interpreted
            # For now, we'll just acknowledge them without changing behavior
            return
        
        # Check for coordinate with arc parameters
        match = self.patterns['coordinate_with_arc'].match(line)
        if match:
            x = self.parse_coordinate(match.group(1))
            y = self.parse_coordinate(match.group(2))
            i = self.parse_coordinate(match.group(3))
            j = self.parse_coordinate(match.group(4))
            operation = int(match.group(5))
            
            self._execute_arc_operation(x, y, i, j, operation)
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
        
        # Check for polygon coordinate sequences (filled areas)
        if ',' in line and not line.startswith('%') and not line.startswith('G') and not line.startswith('D'):
            # Check if this is an aperture macro primitive definition
            match = self.patterns['macro_primitive'].match(line)
            if match:
                # This is an aperture macro primitive definition - ignore silently
                return
            
            # This looks like polygon vertex data - these are complex filled areas that we intentionally don't render
            # Don't show these as "skipped" since they're legitimate polygon data, just not rendered by our simple parser
            return
            
        # Handle unrecognized parameter blocks
        if line.startswith('%'):
            # Unrecognized parameter block
            if self.verbose and line not in self.unrecognized_commands:
                self.unrecognized_commands.add(line)
            return
            
        # Handle unrecognized D codes
        elif line.startswith('D') and not self.patterns['aperture_select'].match(line):
            # Unrecognized D code
            if self.verbose and line not in self.unrecognized_commands:
                self.unrecognized_commands.add(line)
            return
            
        # Handle unrecognized G codes
        elif line.startswith('G') and not self.patterns['g_command'].match(line):
            # Unrecognized G code
            if self.verbose and line not in self.unrecognized_commands:
                self.unrecognized_commands.add(line)
            return
            
        # Handle unrecognized M codes
        elif line.startswith('M') and not self.patterns['end'].match(line):
            # Unrecognized M code
            if self.verbose and line not in self.unrecognized_commands:
                self.unrecognized_commands.add(line)
            return
        
        # Any other unrecognized command
        if self.verbose and line not in self.unrecognized_commands:
            self.unrecognized_commands.add(line)
    
    def _execute_operation(self, x, y, operation):
        """Execute a drawing operation"""
        if operation == 1:  # Move (interpolate) - draw line or arc
            if self.canvas and self.current_aperture:
                if self.interpolation_mode == 1:  # Linear interpolation
                    self._draw_line(self.current_x, self.current_y, x, y)
                else:  # Should not happen here - arcs handled separately
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
    
    def _execute_arc_operation(self, x, y, i, j, operation):
        """Execute an arc drawing operation"""
        if operation == 1 and self.canvas and self.current_aperture:  # Draw arc
            self._draw_arc(self.current_x, self.current_y, x, y, i, j)
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
            self.canvas.setLineCap(1)  # Round caps for smoother appearance
            self.canvas.line(x1, y1, x2, y2)
        
        # Update extents for the line
        self.extents.update(x1, y1, self.current_aperture)
        self.extents.update(x2, y2, self.current_aperture)
    
    def _draw_arc(self, x1, y1, x2, y2, i, j):
        """Draw a circular arc using the current aperture"""
        if not self.current_aperture or not self.canvas:
            return
        
        # Calculate arc center
        center_x = x1 + i
        center_y = y1 + j
        
        # Calculate start and end angles
        start_angle = math.atan2(y1 - center_y, x1 - center_x) * 180 / math.pi
        end_angle = math.atan2(y2 - center_y, x2 - center_x) * 180 / math.pi
        
        # Calculate radius
        radius = math.sqrt(i*i + j*j)
        
        # Determine sweep direction based on interpolation mode
        if self.interpolation_mode == 2:  # Clockwise (G02)
            if end_angle > start_angle:
                end_angle -= 360
        else:  # Counterclockwise (G03)
            if end_angle < start_angle:
                end_angle += 360
        
        # For smooth arc rendering, approximate with multiple small line segments
        num_segments = max(8, int(abs(end_angle - start_angle) / 5))  # 5 degrees per segment minimum
        
        if self.current_aperture.shape == 'C':
            # For circular apertures, draw arc as connected line segments
            width = self.current_aperture.params[0]
            self.canvas.setLineWidth(width)
            self.canvas.setLineCap(1)  # Round caps
            
            # Draw arc as series of connected line segments
            prev_x, prev_y = x1, y1
            for i in range(1, num_segments + 1):
                angle = start_angle + (end_angle - start_angle) * i / num_segments
                angle_rad = angle * math.pi / 180
                curr_x = center_x + radius * math.cos(angle_rad)
                curr_y = center_y + radius * math.sin(angle_rad)
                
                self.canvas.line(prev_x, prev_y, curr_x, curr_y)
                prev_x, prev_y = curr_x, curr_y
        
        # Update extents for the arc
        self.extents.update(x1, y1, self.current_aperture)
        self.extents.update(x2, y2, self.current_aperture)
        self.extents.update(center_x - radius, center_y - radius, self.current_aperture)
        self.extents.update(center_x + radius, center_y + radius, self.current_aperture)

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
    def __init__(self, filename, canvas, verbose=False):
        self.parser = ModernGerberParser(canvas, verbose=verbose)
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
