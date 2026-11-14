"""Generate the anonymous collection worksheet for spec section 8.4."""

import argparse
from pathlib import Path

from problems import default_problems


def render():
    lines = [
        "# Signals and systems — derivation worksheet",
        "",
        "Anonymous participant label: __________    Date: __________",
        "",
        "Please write each intermediate expression, including any work you are unsure about.",
        "Use the right-hand side of the requested quantity, rather than an equation.",
        "Do not put your name, email, or student number on this sheet.",
        "Participation is voluntary; ask the collector how your anonymized work will be used.",
        "",
        "Fourier convention for this worksheet: angular frequency, "
        r"$X(j\omega)=\int_{-\infty}^{\infty}x(t)e^{-j\omega t}\,dt$, no prefactor.",
        "The collector must confirm this matches the course before using these results.",
        "",
        "Solve only the problems assigned by the collector. Leave unattempted problems blank.",
        "",
    ]
    for number, problem in enumerate(default_problems(), 1):
        lines += [f"## {number}. {problem.title}", "", f"Problem ID: `{problem.id}`", "",
                  "$$", problem.given_latex, "$$", ""]
        for index in sorted(problem.family.prompts):
            lines += [f"**Step {index}: {problem.family.prompts[index]}**", "",
                      "________________________________________________________________", "",
                      "________________________________________________________________", ""]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("../data/real/worksheet.md"))
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(), encoding="utf-8")
    print(f"Wrote {args.out}; render Markdown with math support before printing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
