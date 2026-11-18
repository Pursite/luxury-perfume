# Luxury Perfume React storefront

`frontend/` is the customer-facing React application for the Luxury Perfume
API. It uses React 19, Vite 8, React Router 7, plain JavaScript ES modules,
JSX, and plain CSS. Django remains authoritative for authentication, products,
prices, stock, profiles, and owner-bound carts.

## Local setup

Start the backend using the [development guide](../docs/development.md).
Vite runs separately on the host; there is no frontend development Compose service.

Use the Node version declared in [`.nvmrc`](.nvmrc), currently 24.19.0.
[`package.json`](package.json) requires `>=24.15.0 <25`; an older workstation
runtime is not a supported fallback. With `nvm` installed, run from the repository root:

```bash
cd frontend
nvm install
nvm use
node --version
npm ci
npm run dev
```

`npm ci` installs the committed lockfile without regenerating it. Vite binds to
`127.0.0.1` and requests port 5173. Open the URL printed by Vite, normally
`http://127.0.0.1:5173`. It can select another port if 5173 is occupied.

Keep Django running at `http://localhost:8000`. In development, the API base
is empty by default: relative `/api/...` and `/media/...` requests are proxied
by [`vite.config.js`](vite.config.js) to that backend. Absolute image URLs
returned by the API remain absolute. If you change Django's host port, align
the Vite proxy target as well.

The tracked backend development template already includes:

```dotenv
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Preserve existing private `.env` values. If Vite uses another port, align the
origin allowlists before using cookie-backed authentication.

## Checks and production builds

Run these commands from `frontend/`:

| Command | Purpose |
| --- | --- |
| `npm run dev` | Vite development server |
| `npm run lint` | ESLint with zero warnings allowed |
| `npm test` | Vitest once, using jsdom and Testing Library |
| `VITE_API_BASE_URL=https://shop.exonplus.ir npm run build` | Production bundle in ignored `dist/` |

Tests live alongside source files as `*.test.js` / `*.test.jsx`.
[`src/test/setup.js`](src/test/setup.js) installs DOM matchers and cleanup;
[`src/test/fixtures.js`](src/test/fixtures.js) supplies API-shaped fixtures.
See [Testing](../docs/testing.md) for the wider project verification workflow.

A build requires an explicit `VITE_API_BASE_URL`. Vite validates HTTPS and a
root pathname; supply an HTTPS origin without an API path, such as the origin
used by CI above. The client appends `/api/v1/...` paths. Local proxy-based
development does not need this variable. All `VITE_*` values are browser-visible
build configuration, not secrets. Never include Django/JWT keys, database or
Redis credentials, payment/SMS credentials, or private tokens. Changing an
embedded value requires rebuilding the bundle.

### Release pipeline boundary

The [frontend CI job](../.github/workflows/ci.yml) installs dependencies, lints,
tests, builds, and stamps/validates `dist/`. It packages those files in the
`ghcr.io/pursite/luxury-perfume-frontend:<commit-sha>` scratch carrier image.
Publication on `main` depends on the complete release gate and promotes the
archived image without rebuilding it.

The [CD workflow](../.github/workflows/cd.yml) uses the matching SHA artifact.
[`scripts/frontend-release.sh`](../scripts/frontend-release.sh) extracts and
validates a release before atomically switching `frontend-current` under the
configured project directory. The carrier is a filesystem artifact, not a
Node/Vite runtime; normal VPS deployment does not build with npm. SHA-addressed
releases support explicit rollback; CI's short-lived intermediate upload is
not the rollback store. See [Deployment](../docs/deployment.md) for host setup
and operational limits.

## Source organization and routes

```text
src/
├── api/          requests, API errors, token store, and domain clients
├── components/   reusable controls, forms, route guards, and UI states
├── context/      authentication and Cart providers
├── hooks/        context access, SMS capability, and document-title helpers
├── layouts/      persistent Header, page outlet, and development notice
├── pages/        catalogue, product, authentication, Account, Cart, and 404
├── styles/       tokens, global rules, component and page layouts
├── test/         shared test setup and API-shaped fixtures
└── utils/        currency, image, and safe-navigation helpers
```

[`src/App.jsx`](src/App.jsx) defines these routes:

| Route | Behavior |
| --- | --- |
| `/` | Server-filtered product catalogue |
| `/products/:slug` | Product detail, ordered image gallery, and top/heart/base notes |
| `/login` | Username/password sign-in |
| `/signup` | Username/password account creation |
| `/forgot-password` | SMS-dependent password recovery, or an unavailable message |
| `/account` | Protected profile, address, and password forms |
| `/cart` | Protected backend Cart |
| Any other path | Not-found page within the storefront layout |

Product URLs use immutable public slugs. Catalogue search is debounced and
respects IME composition; filters, ordering, and pagination live in the URL.
The controls expose a compact subset of backend-supported filters and use
native selects.

## API client and session ownership

[`src/api/client.js`](src/api/client.js) centralizes URL construction, JSON
requests, bearer headers, refresh, and errors. `ApiError` carries the HTTP
status and response data so forms can display field errors. Network failures
receive a connection message; backend `detail`, `message`, and
`non_field_errors` provide general error text. UI logic must use status/data
contracts rather than branch on exact English error wording.

The access token lives only in JavaScript memory in
[`tokenStore.js`](src/api/tokenStore.js). The backend owns the rotating refresh
token in its persistent `HttpOnly` cookie. Neither token is written to
`localStorage` or `sessionStorage`; token-store initialization removes a legacy
session-storage refresh key. Cookie-backed authentication requests explicitly
include credentials and are subject to backend Origin/CORS checks.

[`AuthContext.jsx`](src/context/AuthContext.jsx) restores the session on startup
through the refresh endpoint. A 401 establishes an anonymous state; network,
429, and server errors expose a retryable restoration error. Protected requests
share an in-flight refresh and retry once after receiving a valid access token.
Where supported, the Web Locks API also serializes cookie-session operations
across tabs. Failed logout keeps the local session and reports an error.

Login and signup establish the same session and accept only validated internal
return paths. [`ProtectedRoute.jsx`](src/components/ProtectedRoute.jsx) waits
for restoration, offers a retry on restoration failure, and redirects anonymous
visitors to Login with a return path. Backend authorization and ownership checks
remain authoritative; a React route guard is only a navigation control.

## Account and password management

[`AccountPage.jsx`](src/pages/AccountPage.jsx) initially loads
`GET /api/v1/users/profile/`. Personal information and address forms keep drafts
in component memory, queue profile writes through
`PATCH /api/v1/users/profile/update/`, and replace displayed profile state with
the returned representation. Personal information includes username, email,
first name, and last name. Existing verified phones are read-only; adding or
verifying a phone remains unavailable in this UI. Address forms edit existing
owned addresses or create the first address when none exists.

[`PasswordManagement.jsx`](src/components/PasswordManagement.jsx) implements
three distinct flows. The backend validates password policy and OTP eligibility;
the frontend also checks required inputs, confirmation, and code format.

| Flow | Requirements and behavior |
| --- | --- |
| Change Password | Authenticated account with `has_usable_password=true`; current password, new password, and confirmation. Does not require SMS. Posts to `/api/v1/users/password/change/`. |
| Initial Set Password | Authenticated OTP-only account without a usable password. Requires an existing username, account phone, and `sms_available=true`. Requests a fresh code through `/api/v1/users/password/set/send-otp/`, then submits it with the new password to `/api/v1/users/password/set/verify/`. |
| Recovery | `/forgot-password` requests a code through `/api/v1/users/password-reset/send-otp/`, then submits phone, code, and new password to `/api/v1/users/password-reset/verify-and-reset/`. Requires operational SMS and an eligible active password account with a registered phone. Does not ask for the current password. |

An OTP-only account without a username is prompted to save one in Personal
Information before initial password setup. Without SMS capability or an account
phone, setup displays an unavailable explanation instead of sending a request.
Recovery request feedback is deliberately generic and does not confirm account
existence. The recovery form accepts an 11-digit phone beginning with `09` and
a six-digit code.

Successful change/setup revokes existing backend refresh sessions, invalidates
old password-bound JWTs, deletes the refresh cookie, clears the frontend access
token, and navigates to `/login` with a prompt to sign in again. Successful
recovery revokes old sessions but issues a replacement session; Auth Context
adopts it and navigates to `/account`. Password/code inputs are cleared after
the final submission attempt.

### SMS capability and unavailable features

[`useSmsAvailability.js`](src/hooks/useSmsAvailability.js) checks
`GET /api/v1/users/auth-capabilities/`. It defaults to unavailable and remains
unavailable on request failure. Login only shows its recovery link when the
response contains `sms_available=true`; a direct visit to `/forgot-password`
shows an unavailable message otherwise. Account password controls use the
profile's `sms_available`, `has_usable_password`, username, and phone fields.

The backend capability checks the SMS enabled setting and registered provider
configuration. The repository has no real registered SMS adapter and the
development template disables SMS. These checks are capability gating, not
proof that a message was delivered. Recovery and initial setup are implemented
but unavailable under that default configuration. Enabling a flag alone does
not supply a provider integration.

SMS sign-in and signup remain disabled controls even if SMS capability becomes
available; they do not call OTP login/signup endpoints. Account phone
verification, customer Orders/Tickets screens, checkout, and online payment
controls remain unavailable. No guest cart or real payment gateway is
implemented in the frontend. The provider-independent Payments backend is also
disabled by default and has no real gateway adapter registered.

## Cart state

[`CartContext.jsx`](src/context/CartContext.jsx) mounts its stateful provider
only for an authenticated session and loads the real owner-bound Cart. It
blocks overlapping client mutations and replaces state with authoritative API
responses. Successful DELETE operations trigger a Cart GET because DELETE
responses have no body. Django supplies current prices, totals, stock, and
availability; unavailable lines are retained. The Cart does not reserve prices
or stock, and browser state is not a durable cart store.

## Design and accessibility

[`DESIGN.md`](DESIGN.md) owns visual intent; do not duplicate or replace it with
page-specific design rules. [`src/styles/tokens.css`](src/styles/tokens.css)
maps that intent into runtime values: dark ink surfaces, warm ivory, restrained
gold, Bodoni Moda display type, and Manrope interface type.
[`global.css`](src/styles/global.css) owns document rhythm, focus, scrollbar,
and reduced-motion behavior; [`components.css`](src/styles/components.css) and
[`pages.css`](src/styles/pages.css) implement responsive UI layouts and variants.

The UI includes a skip link, semantic landmarks, labelled controls, visible
focus, live loading/error feedback, keyboard-operated navigation and
confirmation controls, and reduced-motion styles. Unavailable controls use real
disabled buttons with focusable wrappers for explanatory tooltips; they do not
navigate or send requests. Missing product imagery uses a neutral treatment
rather than simulated product photography.

The customer UI is English. Every route shares the Persian development notice,
marked `lang="fa"` and `dir="rtl"`, that SMS services and online payments are
not available yet. Backend messages may be negotiated in English or Persian;
frontend localization remains deferred.

For wider context, see [Architecture](../docs/architecture.md),
[Authentication](../docs/authentication.md), and [Security](../docs/security.md).
