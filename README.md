# Trip Sajao (PropSaaS) - Headless multi-tenant property management API

FastAPI + PostgreSQL (RLS) + Redis + Celery. Resorts, hotels, houseboats, partner/affiliate system, headless CMS.

## Run (Docker, step by step)
1. Copy `.env.example` to `.env` (it is a hidden file: in a terminal run `ls -a`). Put a key in `COOKIE_ENCRYPTION_KEY`:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
2. `docker compose up -d db redis`
3. `docker compose run --rm api alembic upgrade head`
4. `docker compose run --rm api python -m scripts.create_tenant --name "Demo" --domain demo.example --admin-email you@demo.example --admin-password 'Str0ng-Passw0rd!'`
5. `docker compose up -d --build`
6. Optional demo data: `docker compose exec api python -m scripts.seed_demo --domain demo.example --email you@demo.example --password 'Str0ng-Passw0rd!'`
7. Open **http://localhost:8000/admin/** and sign in (business domain `demo.example`). API docs: http://localhost:8000/docs

The admin console is plain HTML/JS in `app/static/admin` (no Node or build step). Partners sign in on the same page with the "Partner" toggle.

Without Docker for the app: install `requirements.txt`, run `alembic upgrade head`, `uvicorn app.main:app --reload`; settings are read from `.env` automatically. Workers: `celery -A app.workers.celery_app.celery_app worker -l info`, `... beat -l info`, `python -m app.workers.hold_listener`. Checks: `pytest`, and with the API running `python -m scripts.smoke_test --domain ... --email ... --password ...`.

### Updating an existing install
`docker compose up -d --build`, then `docker compose run --rm api alembic upgrade head` (adds the media library, super admin and business-status tables). Rebuilding is also what makes the new **Media** and **Overview** menu items appear; hard-refresh the browser afterwards (Ctrl/Cmd+Shift+R).

## Super admin portal (you, the platform owner)
Create the first super admin, then sign in at **http://localhost:8000/platform/**:
`docker compose run --rm api python -m scripts.create_platform_admin --name "Your Name" --email you@example.com` (it asks for a password of 12+ characters; running it again resets that person's password).
From the portal you can: see all businesses and platform charts; create a business (shows the temporary password and API key once); approve or reject registrations; suspend and reactivate (a suspended business is signed out at once and its website API stops); see each business's usage (properties, rooms, partners, bookings, media storage) and change its limits; reset a business owner's password (they are signed out everywhere); and **sign in as a business** for support. A support session needs a written reason, lasts `SUPPORT_SESSION_MINUTES` (60), shows a banner in their console, cannot change API keys or approve payouts, and every start, end and change is recorded under **Support sessions** and **Audit log** (append-only; the app cannot edit it).
Limits: leave a box empty for "no limit". Over a limit, the business sees a plain message asking them to contact you; nothing is deleted.

## Business registration
Businesses can register themselves at **http://localhost:8000/register/**. `REGISTRATION_MODE` in `.env`: `approval` (default: they wait until you approve), `open` (active at once) or `closed`. It has an IP rate limit, a hidden spam-trap field and a live domain check. No emails are sent yet: tell the owner when approved.

## Overview dashboard
Admin console > **Overview**: bookings, money collected and still owed, occupancy today and for the next 14 days, arrivals, best properties, booking sources and top partners (`/api/v1/reports/overview`, scope `reports:read`).

## Media library
Admin console > **Media**: upload photos (JPG, PNG, WEBP, GIF) and videos (MP4, MOV, WEBM), or add YouTube / Vimeo / direct video links. Every photo or video field in the console (property and unit photos, galleries, blog and event covers, company logo) has a **Choose from library** popup, and you can upload straight from inside it.
Files are stored in the `media` Docker volume (`MEDIA_ROOT`, default `media_store/`) and served publicly at `/media/<tenant>/<file>` with random names. Photos are re-encoded (camera/GPS data removed, scaled to 4000 px) and get a 480 px thumbnail; video thumbnails and durations need `ffmpeg` (included in the Docker image). Limits in `.env`: `MAX_IMAGE_MB` (15), `MAX_VIDEO_MB` (300), `MEDIA_QUOTA_MB` per business (5000). SVG and other formats are refused on purpose. API: `/api/v1/media/*` (scopes `media:read`, `media:write`), documented in the Media > API documentation tab. Check it with `python -m scripts.smoke_media ...`.
Set `PUBLIC_API_BASE_URL` to the address people reach this server at, because it is written into the file addresses.

## Resellers (selling other businesses' rooms)
Any business account can sell rooms of other businesses; there is no separate account type. A business with no properties of its own (for example a travel agency) just uses it this way, and it can add its own properties later.
- **Connect:** Admin console > **Resellers**. A reseller asks an owner (**Rooms I sell > Ask to sell for a business**, using the owner's sign-in domain), or an owner invites a reseller (**Invite a reseller**). The owner sets the terms: commission (fixed amount per night, or percent of the night's price), which **properties** may be sold (optionally a different commission per property), and can **pause, resume or end** at any time.
- **Selling:** the reseller opens **Partner rooms**, searches dates, sees the owner's price and its own commission, holds the room (10 minutes, like everyone) and records the payment. The reseller cannot change the price. The guest pays the **owner directly**; the booking is created in the owner's calendar, so no double booking is possible.
- **Who sees what:** the owner sees all bookings and guests (marked "Sold by ..."); the reseller sees only its own.
- **Commission:** copied onto the booking when the room is held; later changes of terms do not touch it. It is owed after check-out.
- **Commissions menu (statements):** after check-out the commission is written to an append-only commission book (the database user cannot edit or delete it; a cancelled booking adds a negative row). The owner chooses per agreement how it is billed: **monthly** (all finished months, due on a day 1 to 28 of the next month, default the 10th) or **per booking** (due some days after check-out). The owner pays the reseller outside this system, presses **Mark as paid** with a reference, and the reseller presses **I received it** (settled) or **It did not arrive** (disputed; the owner can pay again). Statements past their due date show as late, and the super admin sees them under **Late commissions**. A background task (`channel-statements`, daily 03:00 UTC) does this too, and it also happens whenever someone opens the page.
- **Cancel and refund:** the reseller presses **Cancel...** on a confirmed future booking (Partner rooms > My bookings). The system works out the refund from the **owner's refund rules** (Resellers > Cancellation and refund rules, for example 7+ days before check-in 100%, 3+ days 50%, otherwise 0; these standard rules are used until the owner changes them) and sends the request to the owner. The owner presses **Cancel and refund** (can change the amount, never more than the guest paid) or **Keep the booking** with a reason; the reseller can take a request back. The room is released at once when the owner confirms. The guest's money is with the owner, so the owner refunds the guest directly. Commission already written to the book for that booking is reversed automatically. Not possible once the stay has started.
- **Your own website as a reseller:** API access > create a key with the permissions **channel:read** and **channel:book**. Use `X-API-KEY` and `X-API-SECRET` on: `GET /api/v1/channel/agreements`, `/properties`, `/availability`, `POST /hold`, `POST /confirm`, `GET /bookings`, `GET /bookings/{id}/cancel-quote`, `POST /bookings/{id}/cancel-request`. Every Resellers, Commissions and Partner rooms page has an **API documentation** tab with ready-to-copy examples in cURL, JavaScript and Python.
- **API:** `/api/v1/channel/*`, scopes `channel:read`, `channel:manage`, `channel:book`. Statements: `/api/v1/channel/statements`, `/summary`. Needs `alembic upgrade head` (migrations 0004, 0005 and 0006). Check with `python -m scripts.smoke_channel ...` `python -m scripts.smoke_settlement ...` and `python -m scripts.smoke_cancel ...` (both with the super admin e-mail and password; the second also needs database access to move test bookings into the past, so run it only on a test machine).

## Customers and team

- **Customers** (`/admin` > Customers, API module `customers`): everyone who booked, in one list. Search, groups (repeat guests, never stayed, not seen in 6 or 12 months), tags, notes, bulk tagging and a download that opens in Excel. Customers are created from bookings automatically (matched by email); you can also add one by hand. No emails or SMS are sent yet: "re-targeting" means filtering a group and downloading it.
- **Team** (`/admin` > Team, API module `staff`): staff accounts inside one business. Each person gets a role (Admin, Manager, Staff) and, optionally, their own exact access chosen per area (none / view / edit ...). API keys and team management stay with admins. Switching someone off, or giving a new password, signs them out at once.
- Database change: migration `0007_customers_staff` (run `alembic upgrade head`).

## Events, vendors and budgets

- **Events** (console > Events, API modules `packages` and `events`): keep ready-made **packages** (plan day by day, what is included, a "starting from" price). **Publish an event** from a package by choosing only a date; the plan, price and photo are copied, so later package edits never rewrite events already sold. Websites read published packages and upcoming published events with an API key that has `events:read` (create it under API access). Website content no longer has its own Events page; use Events.
- A package holds: trip details, pickup location, what the budget includes and does not include, health rules, warnings, where guests stay, what to bring, how many days, type of trip (relax, trekking ...), bus type, other transport (CNG, jeep, chander gari, boat ... plus your own), day-by-day plan and photos. **Publish an event** opens the event form already filled from the package; add journey start and end, number of seats, payment ways and the event's own photos, then publish. Database change: migration `0009_trip_details`.
- **Vendors** (console > Vendors, module `vendors`): resorts, restaurants, guides, chander gari, jeep, CNG and boats, place by place, each with its own rates (per night, per person, per trip ...). Staff only; never public.
- **Budgets** (console > Budgets, module `budgets`): the event budget calculator. Add lines from vendor rates or by hand, set the number of people and your margin; the server works out cost, selling price and price per person. Budgets are kept, can be reopened and copied. **Quotation** prints through the browser (choose "Save as PDF"); it shows the company logo, address and phone from Website content > Company, and never the agency's cost or margin.
- Access: standard staff can see events; vendors and budgets (internal costs) are given per person under Team. Database changes: migrations `0008_events_vendors_budgets` and `0009_trip_details`.

## Marketing website
The public website for the product is served at `/` (files in `app/static/site/`). It is bilingual (English and Bengali, with a switch), has an animated header, a "Who gets what" section for owners, partners, resellers and developers, and links to `/register/` and `/admin/`. Edit the words in the `D` table at the top of `site.js`; the page layout is in `index.html` and `site.css`.

## Languages (English and Bengali)
The business console (`/admin`) and the registration page switch between English and Bengali with the language box at the bottom of the menu (or on the sign-in page). The choice is remembered in the browser. The super admin portal stays in English.

English text is the key. Every language is one file in `app/static/admin/js/lang/` (for example `bn.js`) that maps the English text to the translation. Text with changing parts uses `{}`, or `{1}`, `{2}` to reorder them: `"Let {} sell your rooms": "{1}-কে আপনার রুম বিক্রি করতে দিন"`. Server error messages are translated by the same file.

To add a language (say Hindi): (1) add one line to `LANGS` in `app/static/admin/js/i18n.js`; (2) copy `lang/bn.js` to `lang/hi.js` and translate the values; (3) open the console in that language and run `window.__i18nMissing()` in the browser console. It lists every text still in English. Anything not translated simply shows in English.

Business content (property names, blog, events) is not translated by this file. That is the next step.

## How the important parts work
| Concern | Design |
|---|---|
| Tenant isolation | `tenant_id` on every table + RLS policy on `current_setting('app.tenant_id')`, set with `set_config(..., true)` (transaction-local) per request. App DB role is NOBYPASSRLS and not the table owner. Composite FKs `(tenant_id, x_id)` stop cross-tenant references. |
| Pre-auth lookups | `SECURITY DEFINER` SQL functions (`app_tenant_by_api_key`, `app_resolve_vanity`, ...). |
| Overbooking | Per-property advisory lock + overlap check (handles whole-boat vs cabin) + Postgres `EXCLUDE USING gist` constraint as last resort. Redis is **not** the source of truth. |
| 10-min hold | Booking row `HOLD` with DB-clock deadline; Redis key `hold:{tenant}:{booking}` TTL 600; keyspace `expired` event -> `release_hold` task; beat sweep every 60 s guarantees release if an event is missed. |
| Partial payments | `/bookings/confirm` with `payment_mode=PARTIAL` requires >= tenant `deposit_percent`; later calls pay the balance. |
| Commission | Snapshotted on the booking at hold time; accrues proportionally to money received; cancellation posts a reversal; ledger is append-only (no UPDATE/DELETE grant). |
| Payouts | request (<= balance - reserved) -> approve (funds stay reserved) -> mark-paid (ledger debit). |
| Short links | `/go/{code}[/{property-slug}]` -> Fernet-encrypted `_ref_token` (HTTP-only, Secure, SameSite=Lax) -> clean 302. Serve it on the tenant domain via reverse proxy. Headless frontends may forward the cookie value as `X-Ref-Token`. |
| API docs tab | `/api/v1/docs/module/{module}` is generated from the live OpenAPI schema + route scopes, so it can't drift. |

## Deliberate deviations from the brief
Added: `Bookings.check_in/check_out/property_id/commission_amount/payments_json`, `Partners.password_hash`, `Properties.slug`, `Units.layout_json/media_json/capacity`, `UnitType.WHOLE_BOAT/COTTAGE`, extra CMS types (PAGE, ANNOUNCEMENT) + status/slug, `Tenants.api_scopes/settings_json`. Expired holds become `CANCELLED` (`cancel_reason=HOLD_EXPIRED`); "AVAILABLE" is derived from dates.

## Before production
- Implement `verify_payment` in `app/services/booking.py` (currently accepts any reference).
- Add rate limiting at the gateway (login already has a Redis counter), and per-tenant CORS origins.
- Run workers with `DATABASE_URL_SYSTEM` (BYPASSRLS role) only.
- Money is serialised as decimal strings.

## Console layout

The sidebar groups **Website content** into a sub-menu (Company, Blog posts, Galleries, Pages, Announcements); it opens by itself on those pages. The header shows the business logo, name and domain, and the signed-in person with role. Saving Company info updates the header at once.

## Event bookings (API)

A website books seats on a published event with an API key that has `events:book` (create it under API access; keys made before this update must be re-created or edited to add it).

1. `POST /api/v1/events/{id}/hold` - seats and customer details (name, email, phone). The seats are held for the hold time (10 minutes by default). The answer holds a secret `token`; send it as `X-Booking-Token` on the next calls. A partner link (`/go/...` cookie) is attributed automatically.
2. `POST /api/v1/event-bookings/status/{ref}/proof` - upload a screenshot of the manual payment (multipart field `file`).
3. `POST /api/v1/event-bookings/status/{ref}/payment` - method (one of the event's payment methods), amount, transaction id. The booking becomes **Payment to check** and keeps its seats.
4. In the console, **Events > Event bookings**: press **Money received** (the booking is confirmed; the partner earns commission on money really received) or **Reject** (the customer gets a fresh hold time). Balances can be paid later the same way. **Cancel** frees the seats and reverses commission.

`GET /api/v1/event-bookings/status/{ref}` shows progress to the customer. Events now show `seats_left`. Seats count while a booking is confirmed, waiting for a payment check, or held and not yet expired; one event's seats are changed under a row lock, so the last seat can never be sold twice. Guests become customers in Customers. Needs migration `0010`.

## Business profile

Console > **Business profile** (`/api/v1/business`, scopes `business:read`, `business:manage` - saving is admin only): business name, registered name, kind, logo (**required**), owner's photo (**required**) and contact, licence number and expiry, TIN and BIN (optional), other registration, WhatsApp, website, office hours, bank accounts, mobile banking accounts (bKash, Nagad, Rocket, Upay), room and event hold minutes, minimum advance percent, terms and cancellation policy. The logo and name feed the top bar and Website content > Company. The required items are enforced on this page only. A website reads `GET /api/v1/business/public` (scope `cms:read`) to show the logo, licence and the accounts marked "Show to customers"; private details are never included.

## Demo data

`scripts/seed_demo.py` fills a running system with four demo agencies (Bengal Trekker, Zoom Wild, BongTrip, Adventure Trekkers): business profile with logo and owner photo, 3 properties each with rooms, cottages, duplexes or houseboat cabins and prices, 2 packages and 4 events each (one draft), vendors with rates, a budget, sales partners (4 for Bengal Trekker), reseller agreements between the agencies, and sample room and event bookings. It only uses the public API and skips an agency that already exists.

    docker compose exec api python scripts/seed_demo.py --email <super admin email> --password '<super admin password>'

All demo passwords are `Demo-Passw0rd!`; admins are `admin@<domain>` (for example `admin@bengaltrekker.example`). The list is printed and saved as `demo_accounts.txt` in the container's working folder.

## Public website

The marketing site is served by the API itself.

| Address | What it is |
|---|---|
| `/` | Home: the story of one booking from search to the owner's books, every feature, who gets what, developer sample, contact form |
| `/resorts`, `/hotels`, `/houseboats`, `/events` | One page for each kind of business, with its own board, features, booking steps and live listings |

* Text is in English and Bengali (the toggle in the header). Each text carries its Bengali in `data-bn`, so adding a language string means editing the HTML only.
* **Live listings** come from `GET /api/v1/public/showcase?kind=resort|hotel|houseboat|events`. It needs no key and returns only public details (name, place, photo, from-price). A business appears there only after the super admin opens it in the platform console and presses **Feature on website**. `scripts/seed_demo.py` does this for the four demo agencies.
* **Contact form** posts to `POST /api/v1/public/contact` (limited per address and per email, with a hidden field that catches bots). Messages appear in the platform console under **Website messages**.
* Run `alembic upgrade head` once (migration 0011 adds the messages table).
* Test: `PYTHONPATH=. python scripts/smoke_site.py --email <super admin> --password <password>`.
