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
npm run dev   # http://localhost:5175
```

(Note: port is 5175 — 5174 is the POS terminal's renderer dev server.)

Test by posting a message from the dev console:

```js
window.postMessage({ type: "sale", lines: [{ name: "Apple", qty: "2", total: "200" }], total: "200", business: "Khalil GS" }, "*");
```

## Build

```sh
npm run build  # outputs to dist/
```

The pos-terminal Electron process opens this app on the **first
non-primary display** automatically when one is detected, in fullscreen
without window chrome. With a single display attached the customer
window simply does not open — POS flows continue normally.

In dev, the Electron process points the customer window at
`http://localhost:5175` (override with `VITE_CUSTOMER_DISPLAY_URL` if
needed). In prod it loads `customer-display/dist/index.html`.

Driving it from the cashier-side renderer:

```ts
await window.api.customerDisplay.post({
  type: "sale",
  lines: [{ name: "Apple", qty: "2", total: "200" }],
  total: "200",
  business: "Khalil GS",
});
```

`{ success: false }` comes back when no secondary display is attached.
