#!/usr/bin/env python3

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter
import csv
import sys

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
                print(f"Processing: {row[i_dsg]} at {row[i_cx]}")
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

def simple_main():
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
    
    # Create PDF
    canv = canvas.Canvas(base_name + "_assy_simple.pdf", pagesize=letter)
    
    # Load pick and place data
    try:
        pf = PickAndPlaceFileKicad(base_name + ".CSV")
        
        # Process Bottom layer (as per your original code)
        layer = "Bottom"
        ngrp = pf.num_groups(layer)
        print(f"Found {ngrp} component groups in {layer} layer")
        
        for page in range(0, (ngrp + 5) // 6):
            n_comps = min(6, ngrp - page * 6)
            print(f"Processing page {page + 1} with {n_comps} component groups")
            
            # Simple placement without gerber background
            pf.draw(layer, page * 6, n_comps, canv)
            pf.gen_table(layer, page * 6, n_comps, canv)
            canv.showPage()
        
        canv.save()
        print(f"Generated {base_name}_assy_simple.pdf")
        
    except FileNotFoundError:
        print(f"Error: Could not find {base_name}.CSV")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    simple_main()
