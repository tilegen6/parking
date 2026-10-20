"""Check submission structure, traceability, reproducible diagrams and local links."""

import ast
import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from render_submission_diagrams import render

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/pre-defense"


def load(name):
    return json.loads((DOCS / name).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(name):
    return (DOCS / name).read_text(encoding="utf-8")


def research():
    sources = load("sources.json")
    ids = [s["id"] for s in sources]
    require(len(ids) == len(set(ids)), "duplicate source ID")
    science = [s for s in sources if s["type"] == "scientific"]
    peers = [s for s in science if s["peer_reviewed"]]
    require(
        len(sources) >= 12 and len(science) >= 8 and len(peers) >= 8,
        "insufficient literature coverage",
    )
    literature = read("03-literature.md")
    reqids = {r["id"] for r in load("requirements.json")}
    for source in sources:
        require(source["id"] in literature, f"unused source: {source['id']}")
        require(source["url"].startswith("https://"), "source needs primary URL")
        require(
            source["title"] and source["authors"] and source["venue"],
            "incomplete bibliography",
        )
        require(set(source["used_for"]) <= reqids, "source links unknown requirement")
    rows = [
        line
        for line in read("04-systems.md").splitlines()
        if re.match(r"\| [1-8]\. ", line)
    ]
    require(
        len(rows) == 8 and all(len(row.split("|")) == 7 for row in rows),
        "expected four systems compared against eight consistent criteria",
    )
    technology = read("05-technology.md")
    decisions = re.findall(r"## ADR-\d+:.*?(?=\n## |\Z)", technology, re.S)
    require(len(decisions) >= 3, "missing technology decisions")
    for decision in decisions:
        alternatives = [line for line in decision.splitlines() if line.startswith("| ")]
        require(len(alternatives) - 1 >= 3, "decision needs three alternatives")
    print(
        f"{len(sources)} sources; {len(science)} scientific; {len(peers)} peer reviewed"
    )
    print("RESEARCH_VERIFIED")


def traceability():
    requirements = load("requirements.json")
    model = load("diagrams/model.json")
    ids = [r["id"] for r in requirements]
    require(len(ids) == len(set(ids)), "duplicate requirement ID")
    require(
        any(i.startswith("FR-") for i in ids)
        and any(i.startswith("NFR-") for i in ids),
        "missing FR/NFR",
    )
    criteria = read("06-requirements.md")
    evaluation = read("09-evaluation.md")
    procedures = re.findall(r"^\| (T\d+) \|", evaluation, re.M)
    require(len(procedures) == len(set(procedures)), "duplicate verification procedure")
    for requirement in requirements:
        for key in [
            "text",
            "acceptance",
            "verification",
            "components",
            "scenarios",
            "owner",
            "status",
        ]:
            require(requirement.get(key), f"{requirement['id']}: missing {key}")
        require(requirement["priority"] in ["Must", "Should"], "unknown priority")
        require(requirement["id"] in criteria, "requirement absent from human table")
        require(
            requirement["verification"] in procedures, "missing evaluation procedure"
        )
        require(
            set(requirement["components"]) <= set(model["components"]),
            "unknown component",
        )
        require(
            set(requirement["scenarios"]) <= set(model["scenarios"]), "unknown scenario"
        )
        require(
            requirement["owner"] in ["tilegen6", "kimbiled", "sabyrzzhan"],
            "unknown owner",
        )
    print(
        f"{len(ids)} requirements, {len(procedures)} procedures, "
        f"{sum(r['priority'] == 'Must' for r in requirements)} mandatory"
    )
    print("TRACEABILITY_VERIFIED")


class PrototypeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.scripts = []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if attributes.get("id"):
            self.ids.append(attributes["id"])
        if tag == "a":
            self.links.append(attributes.get("href", ""))
        if tag == "script":
            self.scripts.append(attributes)


def artifacts():
    model = load("diagrams/model.json")
    require(len(model["diagrams"]) == 3, "three diagrams required")
    all_nodes = set()
    for diagram in model["diagrams"]:
        svg, dot = render(diagram)
        name = diagram["name"]
        require(read(f"diagrams/{name}.svg") == svg, f"stale {name} SVG")
        require(read(f"diagrams/{name}.dot") == dot, f"stale {name} DOT")
        tree = ET.fromstring(svg)
        require(tree.tag.endswith("svg"), "invalid SVG")
        nodes = {n["id"] for n in diagram["nodes"]}
        all_nodes |= nodes
        for edge in diagram["edges"]:
            source, target = edge[:2]
            require(source in nodes and target in nodes, "broken diagram edge")
        for n in diagram["nodes"]:
            require(
                0 <= n["x"]
                and 0 <= n["y"]
                and n["x"] + n["w"] <= diagram["width"]
                and n["y"] + n["h"] <= diagram["height"],
                "node outside canvas",
            )
    require(
        set(model["components"]) | set(model["scenarios"]) <= all_nodes,
        "diagram missing a referenced component/scenario",
    )
    parser = PrototypeParser()
    parser.feed(read("prototype/index.html"))
    require(len(parser.ids) == len(set(parser.ids)), "duplicate prototype HTML ID")
    require(set(model["scenarios"]) <= set(parser.ids), "prototype misses a scenario")
    require(not parser.scripts, "autonomous mockup must not run remote scripts")
    for link in parser.links:
        if link.startswith("#"):
            require(link[1:] in parser.ids, f"broken prototype target: {link}")
    print(
        f"3 diagram sources/exports; {len(parser.ids)} prototype states/titles checked"
    )
    print("ARTIFACTS_VERIFIED")


SECRET = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def package():
    expected = [
        "00-index",
        "01-proposal",
        "02-relevance",
        "03-literature",
        "04-systems",
        "05-technology",
        "06-requirements",
        "07-architecture",
        "08-prototype",
        "09-evaluation",
        "10-management",
        "11-feedback-access",
        "12-verification-results",
        "13-submission",
    ]
    for name in expected:
        require((DOCS / (name + ".md")).is_file(), f"missing {name}")
    files = [
        ROOT / "README.md",
        *DOCS.rglob("*.md"),
        *DOCS.rglob("*.json"),
        *DOCS.rglob("*.html"),
        *DOCS.rglob("*.svg"),
        *DOCS.rglob("*.dot"),
        *DOCS.rglob("*.txt"),
    ]
    require(SECRET.search("ghp_" + "A" * 40), "secret detector control failed")
    links = 0
    for path in files:
        content = path.read_text(encoding="utf-8")
        require(
            not SECRET.search(content),
            f"credential pattern in {path.relative_to(ROOT)}",
        )
        if path.suffix != ".md":
            continue
        for target in re.findall(r"\]\(([^\s]+)\)", content):
            if target.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target = unquote(urlsplit(target).path)
            resolved = (path.parent / target).resolve()
            require(resolved.is_relative_to(ROOT), "link escapes repository")
            require(resolved.exists(), f"broken local link: {path.name} -> {target}")
            links += 1
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for text in [
        "Aigerim Kydyrbekova",
        "Sabyrzhan Akylbek",
        "tilegen6",
        "kimbiled",
        "sabyrzzhan",
        "docker compose",
        "pytest",
        "npm run build",
        "YouTrack",
    ]:
        require(text in readme, f"README missing {text}")
    require(
        ".env" in (ROOT / ".gitignore").read_text(encoding="utf-8"), "env not ignored"
    )
    print(
        f"{len(files)} submission files, {links} local links; credential control checked"
    )
    print("PACKAGE_VERIFIED")


def readiness():
    rubric = read("rubric.txt")
    presentation = re.findall(r"^(\d+)\t[^\n]+", rubric, re.M)
    steps = re.findall(r"^Step (\d+)\.", rubric, re.M)
    require(
        "Minimum Requirements for the 24 October" in rubric, "minimum section missing"
    )
    minimum = rubric.split("Minimum Requirements for the 24 October", 1)[1]
    items = re.findall(r"^•\s+", minimum, re.M)
    expected = (
        {f"C{int(i):02d}" for i in presentation}
        | {f"G{int(i):02d}" for i in steps}
        | {f"M{i:02d}" for i in range(1, len(items) + 1)}
    )
    require(presentation and steps and items, "rubric sections missing")
    rows = [
        [cell.strip() for cell in line.split("|")[1:-1]]
        for line in read("14-readiness.md").splitlines()
        if re.match(r"\| [CGM]\d{2} \|", line)
    ]
    ids = [row[0] for row in rows]
    require(
        len(ids) == len(set(ids)) and set(ids) == expected, "rubric coverage mismatch"
    )
    counts = collections.Counter()
    for ident, criterion, status, evidence, pending in rows:
        require(criterion and "](" in evidence, f"{ident}: missing artifact link")
        require(
            status in ["Готово", "Частично", "Нужно участие", "Исключено"],
            "unknown readiness status",
        )
        require(
            (status == "Готово") == (pending == "—"),
            f"{ident}: misleading pending state",
        )
        if status == "Исключено":
            require(
                "YouTrack" in criterion and "владельцем" in pending,
                "unsupported exclusion",
            )
        counts[status] += 1
    actions = read("15-needed-from-user.md")
    require(
        set(re.findall(r"^## (U\d+) ", actions, re.M))
        == {f"U{i}" for i in range(1, 6)},
        "missing human action",
    )
    by_id = {r[0]: r for r in rows}
    for ident in ["C02", "C11", "G01", "G02", "G05", "G07", "G09", "M09"]:
        require(
            by_id[ident][2] != "Готово",
            f"{ident}: human/historical evidence not supplied",
        )
    for ident in ["G06", "M08"]:
        require(by_id[ident][2] == "Исключено", "YouTrack is explicitly out of scope")
    print(
        f"{len(rows)} rubric items; ready={counts['Готово']}, "
        f"partial={counts['Частично']}, human={counts['Нужно участие']}, "
        f"excluded={counts['Исключено']}; 5 concrete human actions"
    )
    print("READINESS_VERIFIED")


if __name__ == "__main__":
    modes = {
        "research": research,
        "traceability": traceability,
        "artifacts": artifacts,
        "package": package,
        "readiness": readiness,
    }
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else "all"
        require(mode in [*modes, "all"], "unknown check mode")
        for name, check in modes.items():
            if mode in [name, "all"]:
                check()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(f"SUBMISSION CHECK FAILED: {error}", file=sys.stderr)
        sys.exit(1)
