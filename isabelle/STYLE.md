# Isabelle/Scala source style

Use Isabelle2025-2's `src/Tools/Find_Facts/src/find_facts.scala` and `solr.scala`
as references. Maintain the layout by hand: generic Scala formatters rewrite
Isabelle's section comments and remove the additional spacing between sections.

- Start files with Isabelle's `Title:` comment and a short description.
- Use two-space indentation and explicit braces. Put `else`, `catch`, and
  `finally` on the next line after a closing brace.
- Separate the package, import groups, and top-level definitions with two blank
  lines. Keep closely related declarations and companion definitions together.
- Introduce major sections with `/** section **/`, surrounded by two blank lines
  before and one after. Use `/* subsection */` within a class when useful.
- Leave a blank line between methods. Short related value declarations can stay
  together. Separate local helpers from the statements that use them.
- Aim for 100 columns. Keep expressions together when they fit; break long calls
  at logical argument groups rather than placing every small expression on its
  own line. Align multiline conditions and keep callback parameters with the
  opening brace where practical.
- Preserve external API names and the existing underscore-based application
  naming. Formatting changes should not change behavior or serialized data.

After a style edit, run `isabelle scala_build` and `git diff --check`.
