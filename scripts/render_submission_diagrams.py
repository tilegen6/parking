"""Render editable DOT and SVG from one explicit diagram model; stdlib only."""

import json
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/pre-defense/diagrams"


def text_lines(cx, cy, lines, size=17):
    start = cy - (len(lines) - 1) * 11
    return "".join(
        f'<text x="{cx}" y="{start + i * 22}" text-anchor="middle" '
        f'font-size="{size}">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )


def connection(a, b):
    ax, ay = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    if a["shape"] == "actor":
        ay = a["y"] + 35
    bx, by = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    dx, dy = bx - ax, by - ay
    assert dx or dy, "overlapping node centres"
    sa = min(
        a["w"] / 2 / abs(dx) if dx else float("inf"),
        a["h"] / 2 / abs(dy) if dy else float("inf"),
    )
    if a["shape"] == "actor":
        sa = 0
    sb = min(
        b["w"] / 2 / abs(dx) if dx else float("inf"),
        b["h"] / 2 / abs(dy) if dy else float("inf"),
    )
    return ax + dx * sa, ay + dy * sa, bx - dx * sb, by - dy * sb


def render(diagram):
    width, height = diagram["width"], diagram["height"]
    nodes = {n["id"]: n for n in diagram["nodes"]}
    assert len(nodes) == len(diagram["nodes"])
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img">',
        f"<title>{escape(diagram['title'])}</title>",
        '<defs><marker id="arrow" markerWidth="9" markerHeight="9" '
        'refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" '
        'fill="none" stroke="#527183"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>',
        '<g font-family="Arial, sans-serif" fill="#17354a">',
        text_lines(width / 2, 35, [diagram["title"]], 23),
    ]
    dot = [
        "digraph Parking {",
        "  graph [layout=neato, overlap=false];",
        '  node [fontname="Arial", shape=box];',
    ]
    if "boundary" in diagram:
        x, y, w, h, label = diagram["boundary"]
        svg += [
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            'rx="12" fill="#edf4f8" stroke="#8299a8" '
            'stroke-dasharray="7 5"/>',
            text_lines(x + w / 2, y + 25, [label], 18),
        ]
    for edge in diagram["edges"]:
        source, target, label = edge[:3]
        options = edge[3] if len(edge) > 3 else {}
        a, b = nodes[source], nodes[target]
        x1, y1, x2, y2 = connection(a, b)
        marker = "" if diagram["name"] == "use-cases" else ' marker-end="url(#arrow)"'
        points = options.get("points", [[x1, y1], [x2, y2]])
        route = "M" + " L".join(f"{x},{y}" for x, y in points)
        svg.append(
            f'<path d="{route}" fill="none" '
            f'stroke="#527183" stroke-width="1.6"{marker}/>'
        )
        if label:
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 - 8
            cx, cy = options.get("label_at", [cx, cy])
            svg.append(
                f'<text x="{cx}" y="{cy}" text-anchor="middle" '
                'font-size="14" paint-order="stroke" stroke="#f8fafc" '
                f'stroke-width="5" stroke-linejoin="round">{escape(label)}</text>'
            )
        dot.append(
            f"  {json.dumps(source)} -> {json.dumps(target)} "
            f"[label={json.dumps(label, ensure_ascii=False)}];"
        )
    for node in nodes.values():
        ident, shape = node["id"], node["shape"]
        x, y, w, h = (node[k] for k in ("x", "y", "w", "h"))
        cx, cy = x + w / 2, y + h / 2
        svg.append(f'<g id="{ident}">')
        if shape == "actor":
            svg.append(
                f'<circle cx="{cx}" cy="{y + 12}" r="10" fill="#fff" '
                'stroke="#254e67" stroke-width="2"/>'
            )
            svg.append(
                f'<path d="M{cx},{y + 22} v25 m-20,-16 h40 '
                f'm-20,16 l-17,18 m17,-18 l17,18" fill="none" '
                'stroke="#254e67" stroke-width="2"/>'
            )
            svg.append(text_lines(cx, y + h - 9, [*node["label"], ident], 15))
        elif shape == "usecase":
            svg.append(
                f'<ellipse cx="{cx}" cy="{cy}" rx="{w / 2}" '
                f'ry="{h / 2}" fill="#fff" stroke="#245b77"/>'
            )
            svg.append(text_lines(cx, cy, [ident, *node["label"]]))
        else:
            fill = "#e1f2f3" if shape == "component" else "#fff"
            svg.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'rx="8" fill="{fill}" stroke="#245b77" stroke-width="1.8"/>'
            )
            if shape == "database":
                svg.append(
                    f'<ellipse cx="{cx}" cy="{y + 10}" rx="{w / 2}" '
                    'ry="10" fill="#e4edf2" stroke="#245b77"/>'
                )
            lines = [ident, *node["label"]]
            if shape == "component":
                lines.insert(0, "«component»")
            svg.append(text_lines(cx, cy + 6, lines, 16))
        svg.append("</g>")
        dotshape = {
            "actor": "plaintext",
            "usecase": "ellipse",
            "database": "cylinder",
        }.get(shape, "box")
        label = "\n".join([ident, *node["label"]])
        dot.append(
            f"  {json.dumps(ident)} [label={json.dumps(label, ensure_ascii=False)}, "
            f'shape={dotshape}, pos="{cx / 90},{-cy / 90}!"];'
        )
    svg.append(
        text_lines(
            width / 2,
            height - 18,
            ["Draft · 20.10.2026 · внешние интеграции требуют испытаний"],
            14,
        )
    )
    svg.append("</g></svg>")
    dot.append("}")
    return "\n".join(svg) + "\n", "\n".join(dot) + "\n"


def main():
    model = json.loads((DIRECTORY / "model.json").read_text(encoding="utf-8"))
    for diagram in model["diagrams"]:
        svg, dot = render(diagram)
        (DIRECTORY / (diagram["name"] + ".svg")).write_text(svg, encoding="utf-8")
        (DIRECTORY / (diagram["name"] + ".dot")).write_text(dot, encoding="utf-8")
    print(f"Rendered {len(model['diagrams'])} editable diagrams and SVG exports")


if __name__ == "__main__":
    main()
