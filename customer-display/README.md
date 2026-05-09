# Customer-facing display

A small static React page rendered by the POS terminal Electron process
on a second monitor. See `SCREENS.md` Part B for the design.

## States

The page listens for `window.postMessage` from the POS terminal and
switches between four states:

| Message                               | Screen                                  |
|---------------------------------------|-----------------------------------------|
| `{ type: "idle" }`                    | Promo rotation                          |
| `{ type: "sale", lines, total, ... }` | Live cart preview                       |
| `{ type: "qr", url, amount }`         | Payment QR                              |
| `{ type: "thanks" }`                  | Thank-you (auto-returns to idle in 4s)  |

## Dev

```sh
npm install
npm run dev   # http://localhost:5174
```

Test by posting a message from the dev console:

```js
window.postMessage({ type: "sale", lines: [{ name: "Apple", qty: "2", total: "200" }], total: "200", business: "Khalil GS" }, "*");
```

## Build

```sh
npm run build  # outputs to dist/
```

The pos-terminal Electron process loads `dist/index.html` on the second
monitor when the customer display is enabled in tenant settings.
