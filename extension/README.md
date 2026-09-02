# Dehoarder Bridge extension

Lets the web app list, close, and reopen tabs in the browser profile it's
installed in. Loaded once, manually — there is no store listing.

## Load it (Thorium)

1. Open `thorium://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` directory.
4. Confirm it's running: open `thorium://extensions` and check the service
   worker is active, or watch the Progress view's bridge banner in the web
   app after running `dehoarder serve`.

Reload the extension from `thorium://extensions` after editing
`background.js` or `manifest.json`.

## Testing

```
npm install
npm test
```

`background.js` exports its logic as pure functions so they can be unit
tested with a fake `chrome` object — see `tests/background.test.js`. The
`chrome.runtime` wiring at the bottom of the file only runs inside an
actual extension context.
