# Third-party assets vendored in this folder

| File | Package | Version | License | Source |
|---|---|---|---|---|
| `grapes.min.js`, `grapes.min.css`, `locale/*` | grapesjs | 0.23.6 | BSD-3-Clause (`LICENSE.grapesjs`) | https://www.npmjs.com/package/grapesjs |
| `preset-newsletter.min.js` | grapesjs-preset-newsletter | 1.0.2 | BSD-3-Clause (`LICENSE.preset-newsletter`) | https://www.npmjs.com/package/grapesjs-preset-newsletter |

Regenerate with `scripts\vendor_grapesjs.ps1` (needs npm **once**; the app
itself never calls npm, a CDN or any network service at runtime).

Loaded only by `app/ui/static/js/core/grapesjs_loader.js` when the user opens
`#/builder`; torn down again on route leave.
