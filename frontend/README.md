# EXON+ React storefront

`frontend/` is the customer-facing React application for the Luxury Perfume
API. It uses React 19, Vite, React Router, plain JavaScript, semantic JSX, and
plain CSS. Django remains authoritative for products, authentication, prices,
stock, and carts.

## Local setup

The storefront targets Node 24 LTS. The root workstation's older Node runtime
is not a supported fallback. With `nvm` installed, select the version declared
by `.nvmrc` before installing dependencies:

```bash
cd frontend
nvm install 24
nvm use
node --version
npm ci
```

Run Django at `http://localhost:8000`, then start Vite separately:

```bash
npm run dev
```

The storefront is available at `http://localhost:5173`. Source code uses
relative `/api/...` and `/media/...` URLs in development; Vite proxies both to
`http://localhost:8000`. No frontend Docker service is required.

The local Django `.env` must allow both Vite host spellings:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Do not put Django, JWT, database, Redis, payment, or VPN secrets in a Vite
variable. Every `VITE_*` value is public browser configuration.

## Scripts

```bash
npm run lint
npm test
VITE_API_BASE_URL=https://shop.exonplus.ir npm run build
```

`npm run build` deliberately fails without an explicit HTTPS
`VITE_API_BASE_URL`. Production uses the public setting
`https://shop.exonplus.ir`; it is supplied at build time and is not hard-coded
as an application fallback. Build output is written to ignored `dist/` and is
intended for host-managed Nginx at `https://www.exonplus.ir`.

## Source map

```text
src/
├── api/          centralized requests, errors, JWT refresh, and domain clients
├── components/   focused reusable storefront controls and states
├── context/      Auth and Cart providers
├── hooks/        context access and document-title helpers
├── layouts/      persistent Header, page outlet, and development notice
├── pages/        catalogue, Product Detail, Login, Signup, Cart, and 404 routes
├── styles/       tokens, global rules, components, and page layouts
├── test/         test setup and API-shaped fixtures
└── utils/        currency, image, and safe-navigation helpers
```

`/` is the server-filtered Product catalogue. `/products/:slug` uses the
immutable Product slug and presents the ordered image gallery and real
top/heart/base fragrance notes. `/login` and `/signup` expose the backend's
username/password flows and share one centralized JWT session path. `/cart` is
protected and synchronizes every mutation from the backend response. The
application does not create a guest cart or implement SMS, Orders, checkout,
or payments.

The catalogue exposes a deliberately compact subset of backend-supported
filters. Search is debounced, IME composition is respected, and filters,
ordering, and pagination live in the URL. Native `<select>` elements retain
platform accessibility and interaction behavior.

## Authentication and Cart state

The access token is kept only in JavaScript memory. The rotating refresh token
is kept in `sessionStorage`, so a page reload can restore the session but a
browser session ending removes it. This limits persistence compared with
`localStorage`, but neither storage approach protects a bearer token from
JavaScript running after an XSS compromise. The application therefore keeps
token handling centralized, never logs tokens, retries a protected request
once after a single shared refresh, and returns the whole application to an
anonymous state when refresh fails.

Successful username/password signup establishes the same session as Login,
loads the authenticated Cart, and honors only validated internal return paths.
The Sign In and Create Account pages show disabled SMS alternatives so the
future direction is visible, but those controls do not call any OTP endpoint.

The Cart provider exists only for an authenticated session. It loads the real
owner-bound Cart, blocks overlapping client mutations, and replaces its state
with authoritative API responses. DELETE operations are followed by a Cart
GET because their successful responses have no body. Current prices, totals,
stock, and availability are rendered from Django; unavailable lines are kept.

## Design and interaction contract

The visual system is intentionally restrained: deep black surfaces, warm
ivory text, metallic gold accents, Bodoni Moda display type, Manrope interface
type, thin borders, and low-motion transitions. CSS tokens live in
`src/styles/tokens.css`; responsive behavior is implemented at component and
page breakpoints rather than as a desktop-only layout.

All customer-facing text is English. The layout includes a skip link, visible
focus states, semantic landmarks, labelled controls, live loading/error
states, keyboard-operable navigation and confirmation, and reduced-motion
support. Missing Product imagery uses a neutral EXON+ treatment rather than
fake photography.

The payment and SMS authentication controls are real disabled buttons.
Separate focusable wrappers own their accessible unavailable tooltips; they
never navigate or call an API. Every route includes the understated
development notice that SMS services and online payments are not available
yet.
