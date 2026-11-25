# Performance case studies (Odoo 18, self-hosted)

Real problems measured in a production Odoo 18 deployment used by a wholesale distributor. The method was always
the same: **measure first** (browser automation plus direct RPC timings), find the actual cause, fix that, and
compare against a snapshot so the output did not change. No customer data is included here.

| # | Symptom | Cause | Fix | Result |
|---|---------|-------|-----|--------|
| 1 | Editing one line of a 134-line delivery felt frozen | Every edit triggered a full `onchange` of the whole record, about **2.5 s** each | Override `onchange` to return an empty result when only simple fields of existing lines changed | Edits stay local to the browser; the rest is recomputed on save |
| 2 | Opening a large sales order: **4.6 s** (about 140 lines) and **8.5 s** (207 lines) | A computed "promotion status" column walked the whole order and every loyalty program once **per line** (quadratic) | Compute program/rule per product once and the per-rule total once per order | Same output (checked against a 2,206-line snapshot taken before). That column had accounted for 1.6-4 s of the load; the per-line rescans are gone (post-fix timing not re-measured here) |
| 3 | PDFs of 110-160 lines took **21-31 s** and weighed **4-6.6 MB** | Each product photo was embedded at 1024 px but shown at 90 px | Embed the 256 px thumbnail (about 270 ppp at that size) | **25.4 s to 9.9 s** (6.0 to 1.6 MB), **31.0 s to 10.4 s** (6.6 to 1.8 MB), **21.5 s to 6.6 s** (4.1 to 1.2 MB) |
| 4 | Some product photos printed as an empty box in the PDF | The PDF engine (wkhtmltopdf) does not render WebP | Converted 225 WebP photos to JPEG (quality 95, white background for transparency) | Final timings: 134 lines about 9 s, 159 lines about 8 s, 107 lines about 5 s |
| 5 | In the product catalog, typing a quantity "snapped back" to 1 | (a) each change was sent without waiting for the previous one, so an older request finished last; (b) after the server answered with the price, the framework re-rendered the card and reset the focused `<input>` to the saved value, erasing what was being typed | Serialize requests per card; remember and restore the focused input's value around the framework's patch hooks (`onWillPatch` / `onPatched`) | Reproduced with browser automation by intercepting the save calls: without the fix the typed value was overwritten by a stale one; with it, what the user types is preserved |

## Lessons worth remembering

- `on_change="0"` in a view does **not** disable server-side onchange in Odoo 18: the server forces it on while
  post-processing the view. The place to cut it is the model's `onchange` method.
- In a *lightweight* onchange never return one2many line commands with values (`[1, id, {...}]`): if the server is
  slow, responses arrive out of order and fields flip back (a toggle "turns itself off"). Send auxiliary data through
  a plain field on the parent record instead.
- Hiding list columns with CSS must also hide the matching footer cells, or the hidden columns keep taking width.
- Measure with `fill()` **and** with real keyboard typing while the server response is pending: a quick
  `fill()` plus blur hides race conditions that real users hit.
- `docker ps --filter name=odoo` is a substring match and also returns the database container. Filter on the Swarm
  task name `<service>.1` and insist on exactly one match (see `deploy/deploy.example.sh`).

---

## Resumen en español

Problemas reales medidos en un Odoo 18 en producción. Método: medir primero, atacar la causa real y comparar contra
una foto previa para que el resultado no cambie. Lo más llamativo: PDFs de **25,4 s a 9,9 s** (de 6,0 a 1,6 MB) al
incrustar la miniatura de 256 px en vez de la de 1024 px, y un `onchange` de **~2,5 s por edición** que se evitó
devolviendo un resultado vacío cuando solo cambian campos simples de líneas existentes. Una cantidad que "volvía a 1"
en el catálogo resultó ser una carrera entre envíos y un re-dibujado del campo, no un error de datos.
