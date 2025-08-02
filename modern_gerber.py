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
    def __init__(self, aperture_id, shape, params, macro_name=None):
        self.id = aperture_id
        self.shape = shape  # 'C' for circle, 'R' for rectangle, 'MACRO' for macro
        self.params = params  # list of dimensions
        self.macro_name = macro_name  # for macro apertures
        
    def draw_flash(self, canvas, x, y, parser=None):
        """Draw this aperture as a flash at the given coordinates"""
        if self.shape == 'C':  # Circle
            radius = self.params[0] / 2
            canvas.circle(x, y, radius, stroke=0, fill=1)
        elif self.shape == 'R':  # Rectangle
            w, h = self.params[0], self.params[1]
            canvas.rect(x - w/2, y - h/2, w, h, stroke=0, fill=1)
        elif self.shape == 'MACRO' and parser:  # Macro aperture
            # Look up the macro definition and render it
            if self.macro_name in parser.aperture_macros:
                macro = parser.aperture_macros[self.macro_name]
                macro.render(canvas, x, y, self.params)

class MacroPrimitive:
    """Represents a primitive within an aperture macro"""
    def __init__(self, primitive_type, params):
        self.type = primitive_type
        self.params = params
    
    def render(self, canvas, x_offset, y_offset, macro_params):
        """Render this primitive with given parameters"""
        # Substitute macro parameters ($1, $2, etc.) with actual values
        resolved_params = []
        for param in self.params:
            if isinstance(param, str):
                # Handle expressions like '$1+$1', '$2', '270.000000'
                resolved_value = self.evaluate_macro_expression(param, macro_params)
                resolved_params.append(resolved_value)
            else:
                resolved_params.append(param)
        
        if self.type == 1:  # Circle
            # Format: 1,exposure,diameter,x,y[,rotation]
            if len(resolved_params) >= 4:
                exposure = resolved_params[0]
                diameter = resolved_params[1]
                x = resolved_params[2] + x_offset
                y = resolved_params[3] + y_offset
                if exposure > 0:  # Only draw if exposure is positive
                    radius = diameter / 2
                    canvas.circle(x, y, radius, stroke=0, fill=1)
        
        elif self.type == 4:  # Outline/Polygon
            # Format: 4,exposure,num_points,x1,y1,x2,y2,...,xn,yn[,rotation]
            if len(resolved_params) >= 3:
                exposure = resolved_params[0]
                num_points = int(resolved_params[1])
                if exposure > 0 and len(resolved_params) >= 2 + num_points * 2:
                    # Extract coordinate pairs
                    coords = []
                    for i in range(num_points):
                        x = resolved_params[2 + i * 2] + x_offset
                        y = resolved_params[3 + i * 2] + y_offset
                        coords.extend([x, y])
                    
                    # Draw polygon using reportlab
                    if len(coords) >= 6:  # At least 3 points
                        path = canvas.beginPath()
                        path.moveTo(coords[0], coords[1])
                        for i in range(2, len(coords), 2):
                            path.lineTo(coords[i], coords[i+1])
                        path.close()
                        canvas.drawPath(path, stroke=0, fill=1)
        
        elif self.type == 20:  # Vector line/Rectangle
            # Format: 20,exposure,width,start_x,start_y,end_x,end_y[,rotation]
            if len(resolved_params) >= 6:
                exposure = resolved_params[0]
                width = resolved_params[1]
                start_x = resolved_params[2] + x_offset
                start_y = resolved_params[3] + y_offset
                end_x = resolved_params[4] + x_offset
                end_y = resolved_params[5] + y_offset
                
                if exposure > 0:
                    # Draw as a rectangle between the two points
                    canvas.setLineWidth(width)
                    canvas.line(start_x, start_y, end_x, end_y)
    
    def evaluate_macro_expression(self, expr, macro_params):
        """Evaluate a macro parameter expression like '$1+$1' or '270.000000'"""
        if not isinstance(expr, str):
            return float(expr)
        
        expr = expr.strip()
        
        # If it's just a number, return it
        try:
            return float(expr)
        except ValueError:
            pass
        
        # Handle expressions with $ parameters
        result = expr
        
        # Replace $1, $2, etc. with actual parameter values
        import re
        def replace_param(match):
            param_num = int(match.group(1))
            if param_num <= len(macro_params):
                return str(macro_params[param_num - 1])
            else:
                return '0'  # Default value for missing parameters
        
        result = re.sub(r'\$(\d+)', replace_param, result)
        
        # Now evaluate the mathematical expression
        try:
            # Simple evaluation - be careful about security
            # Only allow basic math operations
            allowed_chars = set('0123456789+-*/.() ')
            if all(c in allowed_chars for c in result):
                return float(eval(result))
            else:
                return 0.0
        except:
            return 0.0

class ApertureMacro:
    """Represents an aperture macro definition"""
    def __init__(self, name):
        self.name = name
        self.primitives = []
    
    def add_primitive(self, primitive):
        self.primitives.append(primitive)
    
    def render(self, canvas, x, y, params):
        """Render this macro at the given position with parameters"""
        for primitive in self.primitives:
            primitive.render(canvas, x, y, params)

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
        if aperture:
            if aperture.shape == 'C':
                margin = aperture.params[0] / 2
            elif aperture.shape == 'R':
                margin = max(aperture.params[0], aperture.params[1]) / 2
            elif aperture.shape == 'MACRO':
                # For macro apertures, use a reasonable default margin
                # Could be improved by analyzing the macro definition
                margin = 1.0  # 1mm default margin for macro apertures
            
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
        self.aperture_macros = {}  # Store macro definitions
        self.current_aperture = None
        self.current_x = 0
        self.current_y = 0
        self.extents = GerberExtents()
        self.format_spec = {'x_digits': 4, 'y_digits': 4, 'decimal_places': 6}
        self.unit_scale = mm  # Default to mm
        self.fg_color = colors.grey
        self.bg_color = colors.lightgrey
        
        # Interpolation mode: 1=linear, 2=clockwise arc, 3=counterclockwise arc
        self.interpolation_mode = 1
        
        # Arc center offset (I, J parameters)
        self.arc_center_i = 0
        self.arc_center_j = 0
        
        # Track unrecognized/skipped commands for verbose output
        self.unrecognized_commands = set()
        self.skipped_commands = set()
        
        # State for parsing aperture macros
        self.current_macro_name = None
        self.current_macro_primitives = []
        self.current_macro_primitive_line = None  # For multi-line primitives
        
        # Regex patterns for Gerber commands
        self.patterns = {
            'format': re.compile(r'%FSLAX(\d)(\d)Y(\d)(\d)\*%'),
            'units': re.compile(r'%MO(MM|IN)\*%'),
            'aperture_def': re.compile(r'%ADD(\d+)([CR]),([0-9.X]+)\*%'),
            'macro_aperture_def': re.compile(r'%ADD(\d+)([^,*]+),?([^*]*)\*%'),  # For macro apertures
            'aperture_select': re.compile(r'D(\d+)\*'),
            'coordinate': re.compile(r'X(-?\d+)Y(-?\d+)D(\d+)\*'),
            'coordinate_with_arc': re.compile(r'X(-?\d+)Y(-?\d+)I(-?\d+)J(-?\d+)D(\d+)\*'),
            'x_only': re.compile(r'X(-?\d+)D(\d+)\*'),
            'y_only': re.compile(r'Y(-?\d+)D(\d+)\*'),
            'arc_params': re.compile(r'I(-?\d+)J(-?\d+)'),
            'g_command': re.compile(r'G0*([123])\*?'),
            'g74_g75': re.compile(r'G(74|75)\*'),
            'aperture_macro_start': re.compile(r'%AM([^*]+)\*$'),
            'aperture_macro_end': re.compile(r'%$'),
            'macro_primitive': re.compile(r'^(\d+),(.+)\*?$'),
            'macro_comment': re.compile(r'^0 .*\*?$'),  # Aperture macro comment primitive
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
    
    def parse_macro_expression(self, expr_str):
        """Parse a macro parameter expression like '$1+$1' or '270.000000'"""
        # For now, keep expressions as strings - they'll be resolved when the macro is used
        return expr_str.strip()
    
    def parse_macro_parameters(self, params_str):
        """Parse comma-separated macro parameters"""
        if not params_str:
            return []
        
        params = []
        # Split by commas but handle expressions
        parts = params_str.split(',')
        for part in parts:
            part = part.strip()
            try:
                # Try to parse as float first
                params.append(float(part))
            except ValueError:
                # Otherwise keep as string (could be an expression like '$1+$1')
                params.append(part)
        return params
    
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
        
        # Check for custom aperture definitions (RoundRect, etc.) - but first check if it's a macro aperture
        if line.startswith('%ADD'):
            # Try macro aperture definition first
            match = self.patterns['macro_aperture_def'].match(line)
            if match:
                aperture_id = int(match.group(1))
                macro_name = match.group(2)
                params_str = match.group(3) if match.group(3) else ""
                
                # Check if this references a known macro
                if macro_name in self.aperture_macros:
                    # Parse macro parameters - split by X and convert to float
                    params = []
                    if params_str:
                        # Split by X (common in macro parameters)
                        param_parts = params_str.split('X')
                        for part in param_parts:
                            try:
                                params.append(float(part) * self.unit_scale)
                            except ValueError:
                                pass
                    self.apertures[aperture_id] = GerberAperture(aperture_id, 'MACRO', params, macro_name)
                    return
                
                # Handle custom apertures (RoundRect, FreePoly, etc.)
                if 'RoundRect' in macro_name or 'FreePoly' in macro_name:
                    # Create fallback approximation as before
                    if 'RoundRect' in macro_name:
                        try:
                            params = self.parse_macro_parameters(params_str)
                            if len(params) >= 9:  # rounding radius + 4 corner coordinates
                                # Use the coordinate extent to determine size
                                x_coords = params[1::2]  # x coordinates
                                y_coords = params[2::2]  # y coordinates
                                width = max(x_coords) - min(x_coords)
                                height = max(y_coords) - min(y_coords)
                                # Create rectangular aperture as approximation
                                self.apertures[aperture_id] = GerberAperture(aperture_id, 'R', [width, height])
                            else:
                                # Fallback to small circle
                                default_size = 0.1 * self.unit_scale
                                self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                        except (ValueError, IndexError):
                            default_size = 0.1 * self.unit_scale
                            self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                    else:
                        # For FreePoly and other custom apertures, create aperture with fallback
                        try:
                            params = self.parse_macro_parameters(params_str)
                            if params and isinstance(params[0], (int, float)) and params[0] > 0:
                                default_size = params[0] * self.unit_scale
                            else:
                                default_size = 0.1 * self.unit_scale
                        except (ValueError, IndexError):
                            default_size = 0.1 * self.unit_scale
                        
                        self.apertures[aperture_id] = GerberAperture(aperture_id, 'C', [default_size])
                    return
            
            # If we get here, it might be a standard aperture definition that the macro pattern caught
            # Fall through to standard aperture definition handling
        
        # Check for aperture macro start
        match = self.patterns['aperture_macro_start'].match(line)
        if match:
            # Start of aperture macro definition
            self.current_macro_name = match.group(1)
            self.current_macro_primitives = []
            self.current_macro_primitive_line = None
            return
        
        # Check for aperture macro end
        if line.strip() == '%' and self.current_macro_name:
            # End of aperture macro definition
            macro = ApertureMacro(self.current_macro_name)
            for primitive in self.current_macro_primitives:
                macro.add_primitive(primitive)
            self.aperture_macros[self.current_macro_name] = macro
            self.current_macro_name = None
            self.current_macro_primitives = []
            return
        
        # Check if we're currently parsing a macro
        if self.current_macro_name:
            # Check for macro comment primitives (primitive 0)
            match = self.patterns['macro_comment'].match(line)
            if match:
                # These are just comments within aperture macros - ignore silently
                return
            
            # Check if we're continuing a multi-line primitive
            if self.current_macro_primitive_line is not None:
                # Append this line to the current primitive
                self.current_macro_primitive_line += line
                
                # Check if this line ends the primitive (ends with % or *%)
                if line.endswith('*%') or line.strip() == '%':
                    # Process the complete primitive
                    primitive_line = self.current_macro_primitive_line
                    self.current_macro_primitive_line = None
                    
                    # Parse the complete primitive
                    match = self.patterns['macro_primitive'].match(primitive_line)
                    if match:
                        primitive_type = int(match.group(1))
                        params_str = match.group(2)
                        
                        # Check if this line ends the macro (ends with %)
                        if params_str.endswith('%'):
                            # Remove the % and process the primitive
                            params_str = params_str[:-1]
                            # Parse the parameters
                            params = self.parse_macro_parameters(params_str)
                            primitive = MacroPrimitive(primitive_type, params)
                            self.current_macro_primitives.append(primitive)
                            
                            # End the macro
                            macro = ApertureMacro(self.current_macro_name)
                            for p in self.current_macro_primitives:
                                macro.add_primitive(p)
                            self.aperture_macros[self.current_macro_name] = macro
                            self.current_macro_name = None
                            self.current_macro_primitives = []
                            return
                        else:
                            # Parse the parameters
                            params = self.parse_macro_parameters(params_str)
                            primitive = MacroPrimitive(primitive_type, params)
                            self.current_macro_primitives.append(primitive)
                            return
                return
            
            # Check for macro primitives
            match = self.patterns['macro_primitive'].match(line)
            if match:
                primitive_type = int(match.group(1))
                params_str = match.group(2)
                
                # Check if this line ends the macro (ends with %)
                if params_str.endswith('%'):
                    # Remove the % and process the primitive
                    params_str = params_str[:-1]
                    # Parse the parameters
                    params = self.parse_macro_parameters(params_str)
                    primitive = MacroPrimitive(primitive_type, params)
                    self.current_macro_primitives.append(primitive)
                    
                    # End the macro
                    macro = ApertureMacro(self.current_macro_name)
                    for p in self.current_macro_primitives:
                        macro.add_primitive(p)
                    self.aperture_macros[self.current_macro_name] = macro
                    self.current_macro_name = None
                    self.current_macro_primitives = []
                    return
                else:
                    # Check if this line ends with *
                    if line.endswith('*'):
                        # Single-line primitive
                        params = self.parse_macro_parameters(params_str)
                        primitive = MacroPrimitive(primitive_type, params)
                        self.current_macro_primitives.append(primitive)
                        return
                    else:
                        # Multi-line primitive - start accumulating
                        self.current_macro_primitive_line = line
                        return
            
            # Check for standalone macro end
            if line.strip() == '%':
                # End the macro
                macro = ApertureMacro(self.current_macro_name)
                for p in self.current_macro_primitives:
                    macro.add_primitive(p)
                self.aperture_macros[self.current_macro_name] = macro
                self.current_macro_name = None
                self.current_macro_primitives = []
                self.current_macro_primitive_line = None
                return
            
            # Any other line inside a macro might be a continuation line
            # If we don't have a current primitive line, this might be a malformed macro
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
                self.current_aperture.draw_flash(self.canvas, x, y, self)
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
