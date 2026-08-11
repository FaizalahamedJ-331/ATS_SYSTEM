"""QR code generation for TOTP setup (SVG data URI, no image libraries).

Uses the tiny, pure-Python ``segno`` library (no Pillow, no C extensions) to
encode the provisioning URI at error-correction level M, then renders the
module matrix as an inline SVG data URI so the setup page needs no extra
static assets.
"""

import base64

import segno


def qr_matrix(text):
    """Return a 2D boolean matrix (True = dark module) for ``text``."""
    qr = segno.make(text, error="m")
    return [[bool(v) for v in row] for row in qr.matrix]


def matrix_to_svg_data_uri(matrix, size=5, quiet=4):
    """Render the matrix as a data-URI SVG (white quiet zone around it)."""
    n = len(matrix)
    dim = (n + quiet * 2) * size
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" shape-rendering="crispEdges">',
        f'<rect width="{dim}" height="{dim}" fill="#ffffff"/>',
    ]
    for r, row in enumerate(matrix):
        for c, dark in enumerate(row):
            if dark:
                x = (c + quiet) * size
                y = (r + quiet) * size
                parts.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" fill="#0b1020"/>')
    parts.append("</svg>")
    svg = "".join(parts)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
