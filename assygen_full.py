#!/usr/bin/env python3

from modern_gerber import GerberMachine, ResetExtents, gerber_extents
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter
import csv
import sys

# Global variables for gerber rendering
gerberPageSize = letter
gerberMargin = 0.75 * 25.4 * mm  # 0.75 inch margin
gerberScale = (1.0, 1.0)
gerberOffset = (0.0, 0.0)

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

        yt = 260 * mm
        canv.setFont("Helvetica", 10)
        canv.setStrokeGray(0)
        canv.setFillGray(0)
        canv.drawString(20 * mm, yt, "Color")
        canv.drawString(40 * mm, yt, "Lib.Reference")
        canv.drawString(80 * mm, yt, "Comment")
        canv.drawString(120 * mm, yt, "Designators")
        n = 0
        for group in parts:
            dsgn = ""
            yt = yt - 6 * mm
            canv.setFillColor(self.col_map[n])
            canv.rect(20 * mm, yt, 10 * mm, 3 * mm, 1, 1)
            canv.setFillGray(0)
            n = n + 1
            for part in group:
                dsgn = dsgn + " " + part.name
            canv.drawString(120 * mm, yt, dsgn)
            canv.drawString(40 * mm, yt, group[0].ref[0:20])
            canv.drawString(80 * mm, yt, group[0].desc[0:20])

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

def renderGerber(base_name, layer, canv):
    """Render Gerber files as background layers"""
    global gerber_extents
    
    if layer == "Bottom":
        f_copper = base_name + ".GBL"
        f_overlay = base_name + ".GBO"
    else:
        f_copper = base_name + ".GTL"
        f_overlay = base_name + ".GTO"

    canv.setLineWidth(0.0)
    gm = GerberMachine("", canv)
    gm.Initialize()
    ResetExtents()
    
    # Render copper layer (light gray)
    gm.setColors(colors.Color(0.85, 0.85, 0.85), colors.Color(0, 0, 0))
    gm.ProcessFile(f_copper)
    
    # Render silkscreen overlay (darker gray)
    gm.setColors(colors.Color(0.5, 0.5, 0.5), colors.Color(0, 0, 0))
    extents = gm.ProcessFile(f_overlay)
    
    return extents

def producePrintoutsForLayer(base_name, layer, canv):
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
        ext = renderGerber(base_name, layer, ctmp)
        ctmp.save()
        
        # Calculate scale and offset to fit page
        if ext and ext[0] != float('inf'):
            scale1 = (gerberPageSize[0] - 2 * gerberMargin) / (ext[2] - ext[0])
            scale2 = (gerberPageSize[1] - 2 * gerberMargin) / (ext[3] - ext[1])
            scale = min(scale1, scale2)
            gerberScale = (scale, scale)
            gerberOffset = (-ext[0] * scale + gerberMargin, -ext[1] * scale + gerberMargin)
            
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

    # Load pick and place data
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
        renderGerber(base_name, layer, canv)
        
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
    for arg in sys.argv[1:]:
        if not arg.startswith('--'):
            base_name = arg
            break
    
    if not base_name:
        print("Usage: assygen <base_name>")
        print("Example: assygen freewatch")
        sys.exit(1)
    
    # Create PDF with full features
    canv = canvas.Canvas(base_name + "_assy.pdf", pagesize=gerberPageSize)
    
    try:
        # Process both top and bottom layers
        # producePrintoutsForLayer(base_name, "Top", canv)
        producePrintoutsForLayer(base_name, "Bottom", canv)
        canv.save()
        
        print(f"\nGenerated {base_name}_assy.pdf with Gerber backgrounds!")
        
    except FileNotFoundError as e:
        print(f"Error: Required file not found - {e}")
        print("Make sure you have the following files:")
        print(f"  - {base_name}.CSV (pick and place data)")
        print(f"  - {base_name}.GTL/.GBL (copper layers)")  
        print(f"  - {base_name}.GTO/.GBO (silkscreen layers)")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
