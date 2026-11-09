# Vendored libraries

Unmodified files from the npm packages below, so that the website works without
network access. Each directory keeps the licence of its package.

| Directory | Package | Files |
| --- | --- | --- |
| `bootstrap` | `bootstrap@5.3.6` (MIT) | `dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js` |
| `latex.js` | `latex.js@0.12.6` (MIT) | `dist/latex.js`, `dist/css/katex.css` |
| `latex.js/fonts` | `latex.js@0.12.6`, identical to `katex@0.13.13` (MIT) | the `KaTeX_*.woff2` fonts that `katex.css` references |

To update, replace the files from the new package versions (`npm pack NAME@VERSION`)
and adjust the versions here.
