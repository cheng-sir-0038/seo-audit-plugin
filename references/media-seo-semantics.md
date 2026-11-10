# Media SEO Semantics

Use only when images/videos are materially part of the user's SEO question.

## Image SEO

Relevant facts can include:

- actual image URL/source used in page HTML/rendered DOM;
- alt text and surrounding page context;
- responsive image sources (`srcset/sizes`) when relevant;
- image landing page status/indexability;
- whether critical images are discoverable/crawlable;
- image structured data/metadata only when relevant to the search feature.

Current PageInspection does not yet expose a media inventory. Without image facts, do not claim an image-level audit from ordinary title/meta inspection.

## Video SEO

Relevant facts can include:

- whether the page is actually a video/watch destination;
- video URL/embed/player discoverability;
- thumbnail/media URLs;
- video structured data when applicable;
- page/video indexability;
- rendered DOM when video information is injected by JavaScript.

Do not assume every page containing an embedded video should behave like a dedicated video result/watch page.

## Rendering interaction

If image/video URLs or metadata appear only after JavaScript, also load `rendering-seo-semantics.md` and distinguish raw HTML from rendered DOM.

## Structured data interaction

Load `structured-data-seo-semantics.md` only when video/product/image markup is part of the claim. Media discoverability and rich-result eligibility are different questions.

## Actions

Recommend the smallest evidence-backed action, for example:

- expose stable crawlable media URLs;
- improve image page context/alt where it is genuinely descriptive;
- ensure video landing/watch pages are accessible and indexable;
- fix missing/incorrect media structured data;
- ensure lazy-loaded media still appears in rendered HTML;
- stop claiming site-wide media issues when only one page was inspected.

## Official facts source
