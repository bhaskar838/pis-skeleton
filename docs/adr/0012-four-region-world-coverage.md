# ADR-0012: Four AWS regions cover the world; launch countries are switched on in the panel
- Status: Accepted
- Date: 2026-11-11
- Spec references: §4.1 (Regions), §8.7; OPEN_QUESTIONS Q3, F4; amends the "India + UK" region assumption

## Context
The founder wants every customer served from the AWS region nearest to them, using as few regions as possible, and
wants to launch in India and Europe first. A tenant's region is fixed at sign-up (its database, key and objects
live there), so the country → region map must be right before customers sign up.

## Decision
1. **Four regions** give every populated place a region within about 150 ms:

   | Region | AWS code | Serves (default map) |
   |---|---|---|
   | Mumbai | `ap-south-1` | South Asia, the Gulf, Iran and Iraq, East Africa and the western Indian Ocean |
   | London | `eu-west-2` | Europe (UK and Crown Dependencies, EU/EEA incl. outermost regions, Switzerland, the Balkans, Eastern Europe, Türkiye, the Caucasus), the Levant, Central Asia, North, West, Central and Southern Africa |
   | N. Virginia | `us-east-1` | North, Central and South America and the Caribbean (EU outermost regions in the Caribbean stay in London) |
   | Singapore | `ap-southeast-1` | East Asia, South-East Asia, Oceania and the Pacific |

   Where latency and law disagree, law wins: places that are legally part of the EU or the UK (Réunion, Guadeloupe,
   French Guiana, Jersey, Gibraltar, …) are always in London.
2. **Data lives in Control DB tables, not code.** `region` (code, name, status `active` / `planned` / `disabled`) and
   `country` (ISO 3166-1 alpha-2 plus Kosovo `XK`, name, region, `signup_enabled`). A migration seeds the default
   map; after that, staff edit it in the panel (Chassis → Regions & countries). Staff can add regions later
   (for example `sa-east-1` or `ap-southeast-2`) and move countries to them.
3. **Launch (F4): India and Europe.** `ap-south-1` and `eu-west-2` are `active`; `us-east-1` and `ap-southeast-1` are
   `planned`. Sign-up is enabled for India and "legal Europe": UK, Crown Dependencies, Gibraltar, EU-27 (incl.
   Åland and the outermost regions), Iceland, Liechtenstein, Norway, Switzerland, Andorra, Monaco, San Marino,
   Vatican City and the Faroe Islands. Every other country gets "DCS-PIS is not available in your country yet".
4. **Rules.** A country can only be enabled for sign-up if its region is `active`. A region cannot be set back to
   `planned` or `disabled` while it has enabled countries or live tenants. Moving a country to another region only
   affects *new* sign-ups: existing tenants keep their region.
5. Activating a region in staging or production assumes its infrastructure (database cluster, KMS, bucket) is
   deployed. Region infrastructure-as-code arrives in P9. Until then only staff admins can activate a region, and
   the runbook requires the stack first.

## Consequences
- Sign-up checks one table row; launching a new country needs no deploy.
- Customers in the Americas and Asia-Pacific cannot sign up until their region is deployed and switched on, or
  until staff deliberately map their country to an active region.

## Alternatives considered
- Six or more regions (adding São Paulo, Sydney, Tokyo, Cape Town): lower latency for some customers, but more
  infrastructure, cost and operations before there is demand. Staff can add them later in the panel.
- Letting customers pick a region: confusing, and it allows residency mistakes.
