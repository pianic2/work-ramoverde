# CMS module (WR-19, WR-20)

`apps/backend/apps/cms` owns the editable structure of the public site: pages built from ordered, typed sections, plus navigation and site-wide settings. Sprint scope is the **foundation only**: models, validation, staff CRUD APIs and public read APIs. There is no React CMS UI and no section components yet; the Django admin is a technical panel.

No second CMS (Wagtail etc.), no Redis/Celery, no cache layer: every public request reads PostgreSQL, so edits are visible on the next call.

## Pages and sections (WR-19)

- `Page`: `title`, `slug` (unique), `status` `DRAFT` / `PUBLISHED` / `ARCHIVED`, `published_at` (set on first publication), per-page SEO (`seo_title`, `seo_description`, `og_image` → `MediaAsset` PROTECT, `canonical_url` https-only, `noindex`), timestamps.
- `PageSection`: `page`, `type`, `variant`, `position` (unique per page), `enabled`, `schema_version`, `content` (JSON), timestamps.

### Section schema registry (`apps/cms/sections.py`)

Decision: a small dependency-free validator (frozen dataclasses: `Text`, `Url`, `Boolean`, `Media`, `IdList`, `Object`, `ListOf`) and a dict registry keyed by `(type, schema_version)`. No `jsonschema` dependency: the rules we need (plain-text checks, URL policy, MediaAsset lookups) are custom anyway, and error paths stay readable (`content.items[1].caption: ...`).

Each entry declares the allowed **variants** and a strict content `Object`:

| Type | v1 variants | Content fields (required in **bold**) |
| --- | --- | --- |
| `hero` | split, image-background, minimal | eyebrow, **heading**, subheading, image (media), primary_cta, secondary_cta |
| `services` | grid, list | heading, intro, service_ids (id list ≤24), cta |
| `projects` | grid, carousel | heading, intro, project_ids (id list ≤24), cta |
| `gallery` | grid, masonry, carousel | heading, intro, **items** (1–48 × {**media**, caption}) |
| `text-media` | media-left, media-right, text-only | heading, **body** (≤5000, multiline), media, cta |
| `stats` | row, grid | heading, **items** (1–8 × {**value**, **label**}) |
| `certifications` | badges, list | heading, intro, certification_ids (id list ≤12) |
| `cta` | banner, card | **heading**, body, cta |
| `contact` | form, details, form-and-details | heading, intro, show_phone, show_address, show_form (contact data comes from SiteSettings) |
| `territory` | map, list | heading, intro, areas (≤40 strings), image |

A link (`cta`, `primary_cta`...) is `{label ≤40, href}`.

Rules enforced on every write:

- Unknown keys rejected at every level; types checked (`bool` is not an int); string length limits.
- **No HTML/JS/CSS anywhere**: text fields reject tags/comments (`<` followed by a letter, `/`, `!`, `?`), `javascript:`/`vbscript:`/`data:text/html`, control characters, and line breaks in single-line fields. Clients render content as text.
- URLs: only `/path`, `#anchor`, `https://host/...`, `tel:+digits`, `mailto:`; no whitespace, backslashes or protocol-relative `//`.
- Media: positive integer `MediaAsset` id that exists, is `PUBLIC` and not `REJECTED`. `PENDING` media may be used in drafts; **publishing** a page requires every referenced media (enabled sections + `og_image`) to be `PUBLIC` and `APPROVED`.
- `services` / `projects` / `certifications` references are id-list **placeholders** (unique positive ints). Those modules don't exist yet; the public API returns the ids unchanged and will resolve them when the modules land (no invented models).

Where validation runs (so no path bypasses it): `PageSection.clean()` (Django admin inline forms), `PageSection.save()` (any ORM save), and the DRF serializer (`run_model_clean`). Reordering uses `bulk_update` of `position` only.

Evolving a schema: add `(type, n+1)` to `_SCHEMAS`. Existing rows keep validating against their stored `schema_version`; new sections default to the latest version.

### Draft-ready publication

- Staff API reads drafts, archived pages and disabled sections.
- Public API serves only `PUBLISHED` pages (others are 404) and only `enabled` sections, ordered by `position`; media ids are replaced by `{id, url, mime_type, width, height, alt_text}` or `null` if the asset is no longer PUBLIC+APPROVED (gallery items whose media disappeared are dropped).
- Changing `status` requires `cms.publish_page` (API and admin).
- Limitation: there are no revisions. Editing a section of a published page is live immediately; a draft/live copy model is a later concern.

### API

| Method & path | operationId | Authorization |
| --- | --- | --- |
| `GET/POST /api/v1/cms/pages` | `listCmsPages` / `createCmsPage` | staff + `cms.view_page` / `cms.add_page` |
| `GET/PATCH/DELETE /api/v1/cms/pages/{id}` | `getCmsPage` / `updateCmsPage` / `deleteCmsPage` | `cms.view_page` / `cms.change_page` (+ `cms.publish_page` to change status) / `cms.delete_page` |
| `GET/POST /api/v1/cms/pages/{page_pk}/sections` | `listCmsPageSections` / `createCmsPageSection` | `cms.view_pagesection` / `cms.add_pagesection` (appended at the end) |
| `GET/PATCH/DELETE .../sections/{id}` | `getCmsPageSection` / `updateCmsPageSection` / `deleteCmsPageSection` | `cms.view_pagesection` / `cms.change_pagesection` / `cms.delete_pagesection` (positions re-compacted) |
| `PUT .../sections/order` | `reorderCmsPageSections` | `cms.change_pagesection`; body `{section_ids: [...]}` must list every section once; positions rewritten in one transaction with the page row locked |
| `GET /api/v1/cms/section-schemas` | `listCmsSectionSchemas` | any active staff (`IsStaffUser`) |
| `GET /api/v1/public/pages/{slug}` | `getPublicPage` | anonymous, published only |

`content` is typed as a free-form object in OpenAPI; its shape is described at runtime by `listCmsSectionSchemas`.

## Navigation, site settings and SEO (WR-20)

- `NavigationMenu`: `key` (unique slug, e.g. `header`, `footer`), `title`.
- `NavigationItem`: `menu`, optional `parent` (**one level** of nesting, same menu; checked in `clean()`), `label` (plain text), exactly one target — `page` (FK, `PROTECT`: a page used by a menu cannot be deleted, API answers 409) **or** `url` (same safe-URL policy as sections) — enforced by `clean()` and a DB `CheckConstraint`; `position`, `visible`.
- `SiteSettings` (singleton, `pk=1`, DB check constraint): `legal_name`, `brand_name`, `vat_number` (11 digits, optional `IT`), `address`, `phone`, `email`, `opening_hours`, `tagline`, `certifications_text`, `primary_cta_label` + `primary_cta_page` **or** `primary_cta_url`, `footer_text`.
- `SEOSettings` (singleton): `default_title`, `default_description`, `default_og_image` (PUBLIC media, `PROTECT`), `allow_indexing` (default **false**: pages are `noindex` until launch is decided).

### Unconfirmed client data stays empty

Every `SiteSettings` field starts blank and **nothing is seeded** (no data migration). Public responses return blank values as `null`. Only facts confirmed by the client Source of Truth may be entered by staff: legal name "RAMO VERDE SRL", brand "RamoVerde", VAT "01637570522", operational address "Località San Marziale 11/13, Colle di Val d'Elsa", phone "05771607653", certifications "ISO 9001", "SOA V CATEGORIA". E-mail, domain, socials, opening hours, founders and slogan are **DA DEFINIRE** and must stay empty. Socials and founders are deliberately not modelled yet.

### Public behavior

- `GET /public/navigation/{key}`: visible items whose target is a `PUBLISHED` page (returned as `page_slug`) or a safe URL (`url`); hidden or unpublished parents hide their children; ordered by `position`. Internal fields (ids, visibility, timestamps) are not exposed.
- `GET /public/site-settings`: company fields (`null` when empty), `primary_cta` (`null` unless it has a label and a public target) and `seo` defaults (og image only if PUBLIC+APPROVED).
- Public page SEO = page values first, then defaults: `title` (seo_title → title), `description` (seo_description → default_description), `og_image` (page → default; only PUBLIC+APPROVED), `noindex` = page.noindex OR NOT allow_indexing, `canonical_url`.
- Public reads never write (singletons read with `current()`, which returns unsaved defaults when absent). No caching anywhere, so edits show up on the next request (tested).

### API

| Method & path | operationId | Authorization |
| --- | --- | --- |
| `GET/POST /api/v1/cms/navigation-menus`, `GET/PATCH/DELETE .../{id}` | `listCmsNavigationMenus`, `createCmsNavigationMenu`, `getCmsNavigationMenu`, `updateCmsNavigationMenu`, `deleteCmsNavigationMenu` | `cms.*_navigationmenu` |
| `GET/POST /api/v1/cms/navigation-menus/{menu_pk}/items`, `GET/PATCH/DELETE .../{id}` | `listCmsNavigationItems`, `createCmsNavigationItem`, `getCmsNavigationItem`, `updateCmsNavigationItem`, `deleteCmsNavigationItem` | `cms.*_navigationitem` |
| `GET/PATCH /api/v1/cms/site-settings` | `getCmsSiteSettings`, `updateCmsSiteSettings` | `cms.view_sitesettings` / `cms.change_sitesettings` |
| `GET/PATCH /api/v1/cms/seo-settings` | `getCmsSeoSettings`, `updateCmsSeoSettings` | `cms.view_seosettings` / `cms.change_seosettings` |
| `GET /api/v1/public/navigation/{key}` | `getPublicNavigation` | anonymous |
| `GET /api/v1/public/site-settings` | `getPublicSiteSettings` | anonymous |

Navigation items are reordered by PATCHing `position` (no bulk reorder endpoint yet).

## Permission codenames (for RBAC role mapping)

Default Django permissions for every model (`view_`, `add_`, `change_`, `delete_`): `page`, `pagesection`, `navigationmenu`, `navigationitem`, `sitesettings`, `seosettings`. Custom: `cms.publish_page` (publish / unpublish / archive). Staff endpoints use `apps.accounts.permissions.StaffModelPermissions` (staff + model permission, view permission required for reads); the section schema catalogue uses `IsStaffUser`.

## Known limits

- No revisions/preview of unpublished edits on published pages; no audit events yet (WR-18 `audit` not available).
- `services`/`projects`/`certifications` ids in sections are not resolved or existence-checked until those modules exist.
- OpenAPI types section `content` as a free-form object.
