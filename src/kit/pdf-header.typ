// kit's PDF look (after the font line kit adds per OS): plain business style, readable tables.
#set par(spacing: 0.9em, leading: 0.6em)
#set table(stroke: 0.5pt + rgb("#bbbbbb"), inset: 6pt)
#show table.cell.where(y: 0): set text(weight: "bold")
#show link: set text(fill: rgb("#1a56b0"))
#show heading: set block(above: 1.3em, below: 0.7em)
#show raw.where(block: true): block.with(fill: luma(245), inset: 8pt, radius: 3pt, width: 100%)
#show quote.where(block: true): it => block(inset: (left: 10pt), stroke: (left: 2pt + luma(190)), it.body)
// pandoc puts each table in a figure; figures do not break across pages, which would cut long tables.
#show figure: set block(breakable: true)
