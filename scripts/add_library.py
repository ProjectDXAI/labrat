#!/usr/bin/env python3
"""Register a local library of purchased books as bibliography entries.

Metadata is curated here rather than scraped from the PDFs. Titles inside these files
are unreliable -- several carry the scanner's filename, a publisher's cover page, or
nothing at all -- and a bibliography that guesses is worse than one that is written down,
because every later judgement about coverage reads from it.

Page counts come from `pdfinfo`, so those are measured rather than declared.

Books with no text layer are registered too, with `acquisition.state: owned` and a note
that they need OCR. That is deliberate: `acquire.py` should be able to see that we hold a
copy which is not yet usable, which is a different problem from not holding one.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# id, filename, title, authors, year, bucket, form, venue, density, priority, tags
LIBRARY: list[dict[str, Any]] = [
    dict(id="wilmott-2006-paul-wilmott-quantitative-finance", file="Paul Wilmott on Quantitative Finance.pdf",
         title="Paul Wilmott on Quantitative Finance", authors=["Paul Wilmott"], year=2006,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="low", priority=3,
         tags=["derivatives", "volatility", "practitioner"]),
    dict(id="fabozzi-2004-mathematics-financial-modeling", file="The Mathematics of Financial Modelling-Fabozzi.pdf",
         title="The Mathematics of Financial Modeling and Investment Management", authors=["Sergio M. Focardi", "Frank J. Fabozzi"], year=2004,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="medium", priority=3,
         tags=["modelling", "investment-management"]),
    dict(id="blyth-2014-introduction-quantitative-finance", file="Introduction to Quantitative Finance.pdf",
         title="An Introduction to Quantitative Finance", authors=["Stephen Blyth"], year=2014,
         bucket="quant_finance_core", form="textbook", venue="Oxford University Press", density="medium", priority=3,
         tags=["derivatives", "pricing"]),
    dict(id="brandimarte-2006-numerical-methods-finance-economics", file="Numerical Methods in Finance and Economics-A MATLAB Based Introduction-Brandimarte.pdf",
         title="Numerical Methods in Finance and Economics: A MATLAB-Based Introduction", authors=["Paolo Brandimarte"], year=2006,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="medium", priority=4,
         tags=["numerical-methods", "monte-carlo", "optimization"]),
    dict(id="kabanov-2006-stochastic-calculus-mathematical-finance", file="From Stochastic Calculus to Mathematical Finance-Kabanov.pdf",
         title="From Stochastic Calculus to Mathematical Finance: The Shiryaev Festschrift", authors=["Yuri Kabanov", "Robert Liptser", "Jordan Stoyanov"], year=2006,
         bucket="mathematical_foundations", form="edited_volume", venue="Springer", density="high", priority=3,
         tags=["stochastic-calculus", "martingales"]),
    dict(id="lyuu-2002-financial-engineering-computation", file="Financial Enginneering & Computation - Principles, Mathematics & Algorithms.pdf",
         title="Financial Engineering and Computation: Principles, Mathematics, Algorithms", authors=["Yuh-Dauh Lyuu"], year=2002,
         bucket="quant_finance_core", form="textbook", venue="Cambridge University Press", density="medium", priority=4,
         tags=["algorithms", "computation", "pricing"]),
    dict(id="shaw-1998-modelling-financial-derivatives-mathematica", file="Modelling Financial Derivatives with Mathematica/Modelling Financial Derivatives with Mathematica.pdf",
         title="Modelling Financial Derivatives with Mathematica", authors=["William T. Shaw"], year=1998,
         bucket="quant_finance_core", form="textbook", venue="Cambridge University Press", density="low", priority=2,
         tags=["derivatives", "symbolic-computation"]),
    dict(id="seydel-2012-computational-finance-numerical-methods", file="Computational Finance Numerical Methods.pdf",
         title="Tools for Computational Finance", authors=["Rüdiger U. Seydel"], year=2012,
         bucket="quant_finance_core", form="textbook", venue="Springer", density="medium", priority=3,
         tags=["numerical-methods", "pde", "monte-carlo"]),
    dict(id="hardle-2002-applied-quantitative-finance", file="Applied Quantitative Finance.pdf",
         title="Applied Quantitative Finance", authors=["Wolfgang Härdle", "Torsten Kleinow", "Gerhard Stahl"], year=2002,
         bucket="quant_finance_core", form="edited_volume", venue="Springer", density="medium", priority=3,
         tags=["risk", "volatility", "applied"]),
    dict(id="fries-2007-mathematical-finance", file="Mathematical Finance-Fries.pdf",
         title="Mathematical Finance: Theory, Modeling, Implementation", authors=["Christian Fries"], year=2007,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="medium", priority=3,
         tags=["interest-rates", "implementation"]),
    dict(id="elliott-2005-mathematics-financial-markets", file="Mathematics of Financial Markets-Elliot.pdf",
         title="Mathematics of Financial Markets", authors=["Robert J. Elliott", "P. Ekkehard Kopp"], year=2005,
         bucket="mathematical_foundations", form="textbook", venue="Springer", density="high", priority=3,
         tags=["martingales", "measure-theory", "pricing"]),
    dict(id="rachev-2008-bayesian-methods-finance", file="Bayesian Methods in Finance.pdf",
         title="Bayesian Methods in Finance", authors=["Svetlozar T. Rachev", "John S. J. Hsu", "Biana S. Bagasheva", "Frank J. Fabozzi"], year=2008,
         bucket="bayesian_statistics", form="textbook", venue="Wiley", density="medium", priority=5,
         tags=["bayesian", "portfolio", "mcmc"]),
    dict(id="capinski-2011-mathematics-for-finance", file="Mathematics for Finance - An Introduction to Financial Engineering-Capinski.pdf",
         title="Mathematics for Finance: An Introduction to Financial Engineering", authors=["Marek Capiński", "Tomasz Zastawniak"], year=2011,
         bucket="quant_finance_core", form="textbook", venue="Springer", density="medium", priority=2,
         tags=["introductory", "pricing"]),
    dict(id="vanderhoek-2006-binomial-models-finance", file="Binomial Models in Finance.pdf",
         title="Binomial Models in Finance", authors=["John van der Hoek", "Robert J. Elliott"], year=2006,
         bucket="quant_finance_core", form="textbook", venue="Springer", density="medium", priority=2,
         tags=["binomial", "discrete-time", "pricing"]),
    dict(id="cherubini-2004-copula-methods-finance", file="Copula Methods in Finance.pdf",
         title="Copula Methods in Finance", authors=["Umberto Cherubini", "Elisa Luciano", "Walter Vecchiato"], year=2004,
         bucket="high_dim_statistics", form="textbook", venue="Wiley", density="high", priority=5,
         tags=["copulas", "dependence", "tail-risk"]),
    dict(id="bartholomewbiggs-2008-nonlinear-optimization-financial", file="Nonlinear Optimization with Financial Applications.pdf",
         title="Nonlinear Optimization with Financial Applications", authors=["Michael Bartholomew-Biggs"], year=2008,
         bucket="optimal_control", form="textbook", venue="Springer", density="medium", priority=5,
         tags=["optimization", "portfolio", "numerical"]),
    dict(id="javaheri-2005-inside-volatility-arbitrage", file="Inside Volatility Arbitrage-Javaheri.pdf",
         title="Inside Volatility Arbitrage: The Secrets of Skewness", authors=["Alireza Javaheri"], year=2005,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="high", priority=4,
         tags=["volatility", "filtering", "state-space"]),
    dict(id="mcnelis-2005-neural-networks-finance", file="Neural Networks in Finance. Gaining Predictive Edge in the Market [McNelis P.D.].pdf",
         title="Neural Networks in Finance: Gaining Predictive Edge in the Market", authors=["Paul D. McNelis"], year=2005,
         bucket="adjacent_disciplines", form="textbook", venue="Elsevier", density="low", priority=2,
         tags=["neural-networks", "forecasting"]),
    dict(id="anon-financial-mathematics-lecture-notes", file="Financial Mathematics.pdf",
         title="Financial Mathematics (lecture notes)", authors=[], year=None,
         bucket="mathematical_foundations", form="lecture_notes", venue=None, density="medium", priority=1,
         tags=["lecture-notes"]),
    dict(id="chen-2008-financial-econometrics-derivatives-pricing", file="Financial Econometrics Modeling Derivatives - Pricing.pdf",
         title="Financial Econometrics Modeling: Derivatives Pricing", authors=["Greg N. Gregoriou", "Razvan Pascalau"], year=2011,
         bucket="quant_finance_core", form="edited_volume", venue="Palgrave Macmillan", density="medium", priority=3,
         tags=["econometrics", "derivatives"]),
    dict(id="tsang-2003-optimal-control-models-finance", file="Optimal Control Models in Finance A New Computational Approach.pdf",
         title="Optimal Control Models in Finance: A New Computational Approach", authors=["Ping Chen", "Sardar M. N. Islam"], year=2005,
         bucket="optimal_control", form="monograph", venue="Springer", density="medium", priority=5,
         tags=["optimal-control", "computational"]),
    dict(id="voit-2005-quantitative-finance-for-physicists", file="Quantitative Finance for Physicists - An Introduction.pdf",
         title="Quantitative Finance for Physicists: An Introduction", authors=["Anatoly B. Schmidt"], year=2005,
         bucket="quant_finance_core", form="textbook", venue="Elsevier", density="low", priority=3,
         tags=["econophysics", "introductory"]),
    dict(id="harrison-2011-mathematical-economics-finance", file="Mathematical Economics and Finance Harrison &  Waldron.pdf",
         title="Mathematics for Economics and Finance", authors=["Michael Harrison", "Patrick Waldron"], year=2011,
         bucket="mathematical_foundations", form="textbook", venue="Routledge", density="medium", priority=2,
         tags=["optimization", "utility", "lecture-notes"]),
    dict(id="kolokoltsov-basics-financial-mathematics", file="Basics of Financial Mathematics.pdf",
         title="Basics of Financial Mathematics", authors=[], year=None,
         bucket="mathematical_foundations", form="lecture_notes", venue=None, density="medium", priority=1,
         tags=["lecture-notes", "introductory"]),
    dict(id="forsyth-2008-computational-finance-without-agonizing-pain", file="Introduction to Computational Finance without Agonizing pain.pdf",
         title="An Introduction to Computational Finance Without Agonizing Pain", authors=["Peter A. Forsyth"], year=2008,
         bucket="quant_finance_core", form="lecture_notes", venue="University of Waterloo", density="high", priority=4,
         tags=["numerical-methods", "pde", "lecture-notes"]),
    dict(id="neftci-2000-financial-derivatives-solution-manual", file="An Introduction to the Financial Derivatives-Neftci/An Introduction to the Mathematics of Financial Derivatives Solution Manual_Neftci.pdf",
         title="An Introduction to the Mathematics of Financial Derivatives: Solution Manual", authors=["Salih N. Neftci"], year=2000,
         bucket="quant_finance_core", form="supplement", venue="Academic Press", density="medium", priority=1,
         tags=["derivatives", "solutions"]),
    # No text layer. Registered so acquire.py can distinguish "held but unusable" from
    # "not held", which are different problems with different fixes.
    dict(id="musiela-2005-martingale-methods-financial-modelling", file="Martingale Methods in Financial Modelling-Musiela.pdf",
         title="Martingale Methods in Financial Modelling", authors=["Marek Musiela", "Marek Rutkowski"], year=2005,
         bucket="mathematical_foundations", form="textbook", venue="Springer", density="high", priority=4,
         tags=["martingales", "term-structure"], needs_ocr=True),
    dict(id="karatzas-1998-methods-mathematical-finance-copy", file="Methods of Mathematical Finance-Karatzas Shreve.pdf",
         title="Methods of Mathematical Finance (local copy)", authors=["Ioannis Karatzas", "Steven E. Shreve"], year=1998,
         bucket="mathematical_foundations", form="textbook", venue="Springer", density="high", priority=4,
         tags=["stochastic-control", "martingales"], needs_ocr=True),
    dict(id="baxter-1996-financial-calculus", file="Financial Calculus An Introduction to Derivative Pricing-Baxter.pdf",
         title="Financial Calculus: An Introduction to Derivative Pricing", authors=["Martin Baxter", "Andrew Rennie"], year=1996,
         bucket="quant_finance_core", form="textbook", venue="Cambridge University Press", density="medium", priority=3,
         tags=["derivatives", "introductory"], needs_ocr=True),
    dict(id="jackel-2002-monte-carlo-methods-finance", file="Monte-Carlo Methods In Finance-Jackel.pdf",
         title="Monte Carlo Methods in Finance", authors=["Peter Jäckel"], year=2002,
         bucket="quant_finance_core", form="textbook", venue="Wiley", density="high", priority=4,
         tags=["monte-carlo", "simulation"], needs_ocr=True),
    dict(id="chan-2009-quantitative-trading", file="Quantitative Trading.pdf",
         title="Quantitative Trading: How to Build Your Own Algorithmic Trading Business", authors=["Ernest P. Chan"], year=2009,
         bucket="practitioner_training", form="trade_book", venue="Wiley", density="low", priority=4,
         tags=["backtesting", "practitioner", "strategy"], needs_ocr=True),
    dict(id="neftci-2000-mathematics-financial-derivatives", file="An Introduction to the Financial Derivatives-Neftci/An Introduction to the Financial Derivatives.pdf",
         title="An Introduction to the Mathematics of Financial Derivatives", authors=["Salih N. Neftci"], year=2000,
         bucket="quant_finance_core", form="textbook", venue="Academic Press", density="medium", priority=3,
         tags=["derivatives", "stochastic-calculus"], needs_ocr=True),
    dict(id="wilmott-1995-mathematics-financial-derivatives", file="The Mathematics Of Financial Derivatives.pdf",
         title="The Mathematics of Financial Derivatives: A Student Introduction", authors=["Paul Wilmott", "Sam Howison", "Jeff Dewynne"], year=1995,
         bucket="quant_finance_core", form="textbook", venue="Cambridge University Press", density="medium", priority=3,
         tags=["derivatives", "pde"], needs_ocr=True),
    dict(id="ross-2011-introduction-mathematical-finance", file="Introduction to Mathematical Finance-Ross.pdf",
         title="An Elementary Introduction to Mathematical Finance", authors=["Sheldon M. Ross"], year=2011,
         bucket="quant_finance_core", form="textbook", venue="Cambridge University Press", density="low", priority=2,
         tags=["introductory", "probability"], needs_ocr=True),
]


def page_count(pdf: Path) -> int | None:
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=120).stdout
        found = re.search(r"^Pages:\s+(\d+)", out, re.M)
        return int(found.group(1)) if found else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register a purchased local library into the bibliography")
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--lab", default="corpus-lab", type=Path)
    parser.add_argument("--today", default="2026-08-06")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    library = args.library.resolve()
    biblio = args.lab / "corpus" / "bibliography.yaml"
    study = args.lab / "corpus" / "study"
    study.mkdir(parents=True, exist_ok=True)

    data = yaml.safe_load(biblio.read_text())
    existing = {e["id"] for e in data["entries"]}

    added, skipped, missing = [], [], []
    for spec in LIBRARY:
        if spec["id"] in existing:
            skipped.append(spec["id"])
            continue
        pdf = library / spec["file"]
        if not pdf.exists():
            missing.append(spec["file"])
            continue
        pages = page_count(pdf)
        needs_ocr = spec.get("needs_ocr", False)
        link = study / f"{spec['id']}.pdf"

        entry = {
            "id": spec["id"],
            "title": spec["title"],
            "authors": spec["authors"],
            "year": spec["year"],
            "bucket": spec["bucket"],
            "form": spec["form"],
            "venue": spec["venue"],
            "identifiers": {"isbn": None, "doi": None, "url": None},
            "pages": pages,
            "density": spec["density"],
            "priority": spec["priority"],
            "rights": {
                "status": "licensed_purchase_required",
                "confidence": "confirmed",
                "evidence": "Purchased copy held locally.",
                "checked_at": args.today,
                "grant": None,
                "notes": "Owned copy, read locally. Redistribution is a separate question and this is not a grant for it.",
            },
            "acquisition": {
                "state": "owned",
                "copy_path": f"corpus/study/{spec['id']}.pdf",
                "source_url": None,
                "obtained_at": args.today,
                "note": (
                    "Local library, no text layer; needs OCR before it is readable."
                    if needs_ocr
                    else "Local library, text layer present."
                ),
            },
            "units": [],
            "refs": [],
            "discovered": {"round": 0, "method": "local_library", "source": str(library)},
            "status": "candidate",
            "tags": spec["tags"] + (["needs-ocr"] if needs_ocr else []),
            "notes": None,
        }
        added.append(entry)
        if not args.dry_run:
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(pdf)

    if not args.dry_run and added:
        data["entries"].extend(added)
        biblio.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100))

    print(json.dumps({
        "added": len(added),
        "with_text_layer": sum(1 for s in LIBRARY if not s.get("needs_ocr") and s["id"] in {a["id"] for a in added}),
        "needs_ocr": sum(1 for s in LIBRARY if s.get("needs_ocr") and s["id"] in {a["id"] for a in added}),
        "pages": sum(a["pages"] or 0 for a in added),
        "skipped_existing": skipped,
        "file_not_found": missing,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
