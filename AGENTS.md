# MOCAviz Agent Notes

## Browser Checks

- Use `scripts/chromium_probe.mjs` for reusable Chromium/Playwright checks of JS pages in this repo.
- The approved out-of-sandbox command prefix is:

```bash
node scripts/chromium_probe.mjs
```

- Prefer this helper over one-off Playwright snippets when verifying rendered JS pages, Plotly content, selector counts, text, screenshots, or basic interactions.
- Example:

```bash
node scripts/chromium_probe.mjs \
  --url 'http://127.0.0.1:8074/js/spectral-index-explorer?mock=1&dbase=mocadb_private_tables' \
  --wait-js "document.querySelector('#sie-plot')?.data?.length > 0" \
  --expect-plotly "#sie-plot::traces>=1,shapes>=2" \
  --expect-count "#sie-band-table tbody tr>=2" \
  --screenshot /private/tmp/sie_probe.png
```
